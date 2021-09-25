from modules.comms import TCPServers
from modules.comms.TCPQueueCommunicator import TCPQueueCommunicator
import mcstatus
from queue import Queue, Empty
import threading
import sys
from enum import Enum
import subprocess
import configparser
import os
import re
import json
import socket
from root import *
from functools import total_ordering
from modules.comms.MCMainToPCW import MCCommandSet, FormattedMsg
from misc.ColorLogBase import ColorLogBase
import time
import datetime

class CommandSet(Enum):

    HELLO = 'hello'
    MCALIVE = 'mc_alive'
    MCSTATUS = 'mcstatus'
    LAUNCH = 'launch_mc'
    SHUTDOWN = 'kill'
    DEALLOCATE = 'stop'
    ABORT = 'abort'
    REQUESTSTATE = 'request_state'
    PASSMSG = 'pass_msg'
    RESTART = 'restart'


class MCServer(ColorLogBase):
    def __init__(self, config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg'), **kwargs):
        super().__init__()
        self.config = configparser.ConfigParser()
        self.config.read(config)
        self.mcport = 25565
        self.api_port = int(self.config.get('POOL', 'api_port'))
        self.minecraft_api_port = int(self.config.get('POOL', 'mc_api_port'))
        self.comms = None
        self.in_queue = Queue()
        self.out_queue = Queue()
        self.minecraftserver = None
        self.has_rest = kwargs.get('pp', True)     # By Default - run polycraft with Private Properties
        self.state = MCServer.State.STARTING

    @total_ordering
    class State(Enum):
        STARTING = -1
        ACTIVE = 0
        REQUESTED_DEACTIVATION = 1
        DEACTIVATED = 2
        REQUESTED_RESTART = 3
        CRASHED = 99

        def __lt__(self, other):
            if self.__class__ is other.__class__:
                return self.value < other.value
            return NotImplemented


    def _launch_comms(self):
        # in_queue = Queue()
        # out_queue = Queue()
        self.log.debug("launching comms")
        lock = threading.Lock()
        self.comms = TCPQueueCommunicator(  in_queue=self.in_queue,
                                            out_queue=self.out_queue,
                                            tm_lock=lock,
                                            port=self.api_port)

        self.comms.setDaemon(True)
        self.comms.start()
        self.log.info("Comms Launched")

    def _check_queues(self):
        """
        Check the STDOUT queues in both the PAL and Agent threads, logging the responses appropriately
        :return: next_line containing the STDOUT of the PAL process only:
                    used to determine game ending conditions and update the score_dict{}
        """
        next_line = b''

        # # write output from procedure A (if there is any)
        # DN: Remove "blockInFront" data from PAL, as it just gunks up our PAL logs for no good reason.
        try:
            next_line = self.in_queue.get(False, timeout=0.025)
            self.log.debug(f"input: {next_line}")
            # self.PAL_log.message_strip(str(next_line))
            sys.stdout.flush()
            sys.stderr.flush()
        except Empty:
            pass

        return str(next_line, TCPServers.ENCODING, 'ignore')

    def check_and_send_msg(self, msg: FormattedMsg):
        """
        Wrapper to send messages by first checking to see if the server is up/receivable
        :param msg:
        :return: False if the send message thread could not be launched.
        """
        if self.test_mc_status():
                thread = threading.Thread(target=self.send_message_to_minecraft_api, args=(msg,))
                thread.start()
                return True
        return False

    def send_message_to_minecraft_api(self, msg: FormattedMsg):
        """
        Ensure that the server is up before trying to run this command.

        Valid cmd for MC:
        SAY - prints messages to all players on the server
        DEALLOC - shuts down the server in 10 minutes, transitioning players to ip VALUE
        KILL - immediately shuts down the server

        :param msg: msg to send - must be a FormattedMsg obj with format: {"cmd": "{CMDNAME}", "arg": "{VALUE}"}
        :return: N/A    # TODO: capture returns from MC?
        """

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(('127.0.0.1', self.minecraft_api_port))
            self.log.debug(f"sending data to the server: {msg.msg}")
            sock.sendall(bytes(msg.msg + "\n", "utf-8"))
            self.log.debug("data sent!")
            received = str(sock.recv(1024), "utf-8")
            self.log.debug(f"received data from the server: {received}")
            return True


    def __check_and_launch_minecraft(self):

        if self.test_mc_status():
            return False
        else:
            return self._launch_minecraft()

    def launch_minecraft_script(self, script_name: str = "run_polycraft_no_pp.sh", script_args: str ="oxygen"):
        """
        Runs a script to (re)launch minecraft.
        NOTE: RUNS UNCHECKED!!!

        :script_name: name of script in the scripts/ folder.
        :return: True (always)
        """
        script = "./" + script_name
        self.log.info(f"Running command: {script} {script_args}")
        self.minecraftserver = subprocess.Popen(f'{script} {script_args}',
                                                shell=True,
                                                cwd=os.path.join(ROOT_DIR, 'scripts/'),
                                                universal_newlines=True,)
        return True


    def _launch_minecraft(self):

        script = './run_polycraft_no_pp.sh'
        # if not self.has_rest:
        #     script = './run_polycraft_no_pp.sh'

        self.log.debug(f"Did kwargs set has_rest? {self.has_rest}")

        self.minecraftserver = subprocess.Popen(f'{script} oxygen',
                            shell=True,
                            cwd=os.path.join(ROOT_DIR, 'scripts/'),
                            # stdout=subprocess.PIPE,
                            # stderr=subprocess.STDOUT,
                            # bufsize=1,  # DN: 0606 Added for performance
                            # universal_newlines=True,  # DN: 0606 Added for performance
                         )

        return True

    def test_mc_status(self):
        try:
            serv = mcstatus.MinecraftServer.lookup("127.0.0.1:25565")
            val = serv.status()
            self.log.debug(val.raw)
            # self.out_queue.put(val.raw)
            if self.state == MCServer.State.STARTING:
                self.state = MCServer.State.ACTIVE
            return True
        except Exception as e:
            if self.state == MCServer.State.ACTIVE:
                self.state = MCServer.State.CRASHED
            elif self.state == MCServer.State.REQUESTED_DEACTIVATION:
                self.state = MCServer.State.DEACTIVATED

            self.log.error("Err: Server is not up")
            return False
            # self.out_queue.put("Err: Server is not alive")

    def parse_deallocate_msg(self, line):
        """
        Expected Format:
        b'stop {"IP":"123.45.12.20", "PORT":1223}\n'
        """
        line_end_str = os.linesep
        if line.find('{') != -1 and line.find(line_end_str) != -1:
            # Get timestamp:
            json_text = line[line.find('{'):line.find(line_end_str)]

            data_dict = json.loads(json_text)
            if 'IP' in data_dict and 'PORT' in data_dict:
                return data_dict['IP'], data_dict['PORT']

        return None

    def altparse_deallocate_msg(self, line):
        """
        Expected Format:
        b'stop {"IP":"123.45.12.20", "PORT":1223}\n'
        """
        line_end_str = os.linesep
        if line.find('{') != -1 and line.find('}') != -1:
            # Get timestamp:
            json_text = line[line.find('{'):line.find('}')+1]

            data_dict = json.loads(json_text)
            if 'IP' in data_dict and 'PORT' in data_dict:
                return data_dict['IP'], data_dict['PORT']

        return None

    def run(self):
        stay_alive = True
        self._launch_comms()
        self.__check_and_launch_minecraft()
        while stay_alive:
            next_line = self._check_queues()

            if next_line is None or next_line == '':
                time.sleep(0.05)
                now = datetime.datetime.now()
                if now.hour == 3 and now.minute == 0 and now.second == 0:
                    self._launch_minecraft()
                    time.sleep(12)
                # elif now.minute % 10 == 0 and now.second == 0:
                #     self._launch_minecraft()
                #     time.sleep(12)

                ## Handle the restart request. Useful for CI.
                elif self.state == self.State.REQUESTED_RESTART:
                    self.log.info("Requested Restart of the system. Waiting for the server to launch")
                    self.state = self.State.STARTING
                    if not self.test_mc_status():

                        self.log.info("Waiting for server to shutdown gracefully.")
                        time.sleep(12)
                continue

            if not self.comms.is_alive():
                self.log.error("Unable to run the API Thread. Do I need a fresh node?")

            if CommandSet.HELLO.value in next_line.lower():
                self.out_queue.put("I am awake")

            elif CommandSet.ABORT.value in next_line.lower():
                self.log.warning(f"abort received... checking if MC is running:")
                if self.state == self.State.REQUESTED_RESTART:
                    self.log.info("Aborting this script as server restarts...")
                    self.out_queue.put("Aborting...")
                    stay_alive = False
                elif self.test_mc_status():
                    self.log.warning("Alert: Aborting this script without killing MC?")
                    self.out_queue.put("Aborting...")
                    stay_alive = False
                elif self.state == self.State.STARTING:
                    self.log.warning("Alert: Aborting this script while still starting MC.")
                    self.out_queue.put("Aborting...")
                    stay_alive = False
                else:
                    self.log.error("MC not running. [FORCE] abort this script without state loss...?")
                    self.out_queue.put("ALERT! MC Not Alive")
                    #stay_alive = False


            elif CommandSet.LAUNCH.value in next_line.lower():
                self.log.warning(f"(Re)Launching MC Server")
                self._launch_minecraft()
                self.out_queue.put("Re-launching MC Server")

            elif CommandSet.MCALIVE.value in next_line.lower():
                self.log.debug("is MC Alive?")
                if self.test_mc_status():
                    self.out_queue.put("Server is Up!")
                else:
                    self.out_queue.put("Err: Server is not alive")

            elif CommandSet.DEALLOCATE.value in next_line.lower():
                self.log.warning("requesting decommission...")
                if not self.test_mc_status():
                    self.log.error("Critical error! Server is not active")
                    self.out_queue.put("Err: Server is not active")
                else:
                    targetIP = self.altparse_deallocate_msg(next_line)
                    args = "NONE"
                    if targetIP is None:
                        self.out_queue.put("Deallocating Server")
                        msg = FormattedMsg(MCCommandSet.KILL)
                        self.check_and_send_msg(msg)

                        # self.send_message_to_minecraft_api(msg)
                    else:
                        self.out_queue.put(f"Deallocating Server. Sending Players to {targetIP}")
                        args = "{" + f'"IP":"{targetIP[0]}", "PORT":{targetIP[1]}' + "}"
                        msg = FormattedMsg(MCCommandSet.DEALLOC, f"{targetIP[0]}:{targetIP[1]}")
                        self.check_and_send_msg(msg)
                        # self.send_message_to_minecraft_api(msg)

                    ## Update State
                    self.state = MCServer.State.REQUESTED_DEACTIVATION

            elif CommandSet.PASSMSG.value in next_line.lower():
                self.log.info("Sending msg to Server")
                nl = re.sub(rf"{CommandSet.PASSMSG.value}", "", next_line.lower()).strip()
                msg = FormattedMsg(MCCommandSet.SAY, nl)
                if self.check_and_send_msg(msg):
                    self.out_queue.put(f"Sent message to server")
                else:
                    self.out_queue.put(f"Error: Server is not active!")

            elif CommandSet.RESTART.value in next_line.lower():
                self.log.warning("(Force) Restarting Minecraft...")
                if not self.test_mc_status():
                    self.log.error("Cannot restart - MC is not up.")
                    self.out_queue.put("Error: Server is not active and cannot restart")

                else:
                    #self.log.error("Killing Server...")
                    #self.check_and_send_msg(FormattedMsg(MCCommandSet.KILL))
                    self.launch_minecraft_script("update_git_and_restart_polycraft.sh",
                                                 script_args="$HOME/polycraft/ " +
                                                             f"/home/polycraft/{self.config.get('SERVER','worldName')} "
                                                             + f"{self.config.get('SERVER','worldName')}")
                    self.state = MCServer.State.REQUESTED_RESTART
                    self.out_queue.put("Restarting Server.")

            elif CommandSet.MCSTATUS.value in next_line.lower():
                self.log.debug("Testing: MCSTATUS")
                if self.test_mc_status():
                    self.out_queue.put("Server is Up!")
                else:
                    self.out_queue.put("Err: Server is not alive")

            elif CommandSet.REQUESTSTATE.value in next_line.lower():
                self.log.debug(f"Requesting MC State: {self.state.value}")
                self.test_mc_status() # Update the state.
                self.out_queue.put(f'{{"State":{self.state.value}}}')

            else:
                self.log.warning("unknown command")
                self.out_queue.put("Err: Unknown Command")

        self.comms.kill()
        self.comms.join(5)


if __name__ == '__main__':
    serv = MCServer(pp=False)
    serv.log.info(f"Launching MC Listener Thread on Port: {serv.api_port}")
    serv.run()