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
import json
import socket
from root import *
from functools import total_ordering

class CommandSet(Enum):

    HELLO = 'hello'
    MCALIVE = 'mc_alive'
    MCSTATUS = 'mcstatus'
    LAUNCH = 'launch_mc'
    SHUTDOWN = 'kill'
    DEALLOCATE = 'stop'
    ABORT = 'abort'
    REQUESTSTATE = 'request_state'


class MCServer:
    def __init__(self,  config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg'), **kwargs):
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
        CRASHED = 3

        def __lt__(self, other):
            if self.__class__ is other.__class__:
                return self.value < other.value
            return NotImplemented


    def _launch_comms(self):
        # in_queue = Queue()
        # out_queue = Queue()
        print("launching comms")
        lock = threading.Lock()
        self.comms = TCPQueueCommunicator(  in_queue=self.in_queue,
                                            out_queue=self.out_queue,
                                            tm_lock=lock,
                                            port=self.api_port)

        self.comms.setDaemon(True)
        self.comms.start()
        print("Comms Launched")

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
            print(f"input: {next_line}")
            # self.PAL_log.message_strip(str(next_line))
            sys.stdout.flush()
            sys.stderr.flush()
        except Empty:
            pass

        return str(next_line, TCPServers.ENCODING)

    def send_message_to_minecraft_api(self, msg):
        """
        Run this using a thread
        :param msg: msg to send
        :return: N/A
        """

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(('127.0.0.1', self.minecraft_api_port))
            print("sending data to the server...")
            sock.sendall(bytes(msg + "\n", "utf-8"))
            print("data sent!")
            received = str(sock.recv(1024), "utf-8")
            print(f"received data from the server: {received}")
            return True



    def _launch_minecraft(self):

        script = './run_polycraft.sh'
        if not self.has_rest:
            script = './run_polycraft_no_pp.sh'

        print(f"Did kwargs set has_rest? {self.has_rest}")

        self.minecraftserver = subprocess.Popen(f'./run_polycraft_no_pp.sh oxygen',
                            shell=True,
                            cwd=os.path.join(ROOT_DIR, 'scripts/'),
                            # stdout=subprocess.PIPE,
                            # stderr=subprocess.STDOUT,
                            # bufsize=1,  # DN: 0606 Added for performance
                            # universal_newlines=True,  # DN: 0606 Added for performance
                         )

    def test_mc_status(self):
        try:
            serv = mcstatus.MinecraftServer.lookup("127.0.0.1:25565")
            val = serv.status()
            print(val.raw)
            # self.out_queue.put(val.raw)
            if self.state == MCServer.State.STARTING:
                self.state = MCServer.State.ACTIVE
            return True
        except Exception as e:
            if self.state == MCServer.State.ACTIVE:
                self.state = MCServer.State.CRASHED
            elif self.state == MCServer.State.REQUESTED_DEACTIVATION:
                self.state = MCServer.State.DEACTIVATED

            print("Err: Server is not up")
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
                return (data_dict['IP'], data_dict['PORT'])

        return None

    def run(self):
        stay_alive = True
        self._launch_comms()
        self._launch_minecraft()
        while stay_alive:
            next_line = self._check_queues()

            if next_line is None or next_line == '':
                continue

            if CommandSet.HELLO.value in next_line.lower():
                self.out_queue.put("I am awake")

            elif CommandSet.ABORT.value in next_line.lower():
                print(f"abort received...")
                self.out_queue.put("Aborting...")
                stay_alive = False

            elif CommandSet.LAUNCH.value in next_line.lower():
                print(f"(Re)Launching MC Server")
                self._launch_minecraft()
                self.out_queue.put("Re-launching MC Server")

            elif CommandSet.MCALIVE.value in next_line.lower():
                print("is MC Alive?")
                if self.test_mc_status():
                    self.out_queue.put("Server is Up!")
                else:
                    self.out_queue.put("Err: Server is not alive")

            elif CommandSet.DEALLOCATE.value in next_line.lower():
                print("requesting decommission...")
                if not self.test_mc_status():
                    print("Critical error! Server is not active")
                    self.out_queue.put("Err: Server is not active")
                else:
                    targetIP = self.parse_deallocate_msg(next_line)
                    args = "NONE"
                    if targetIP is None:
                        self.out_queue.put("Deallocating Server")
                    else:
                        self.out_queue.put(f"Deallocating Server. Sending Players to {targetIP}")
                        args = "{" + f'"IP":"{targetIP[0]}", "PORT":{targetIP[1]}' + "}"

                    self.send_message_to_minecraft_api(args)  ## TODO: Should this be a separate thread?

            elif CommandSet.MCSTATUS.value in next_line.lower():
                print("Testing: MCSTATUS")
                if self.test_mc_status():
                    self.out_queue.put("Server is Up!")
                else:
                    self.out_queue.put("Err: Server is not alive")

            elif CommandSet.REQUESTSTATE.value in next_line.lower():
                print(f"Requesting MC State: {self.state.value}")
                self.test_mc_status() # Update the state.
                self.out_queue.put(f'{{"State":{self.state.value}}}')

            else:
                print("unknown command")
                self.out_queue.put("Err: Unknown Command")

        self.comms.kill()
        self.comms.join(5)


if __name__ == '__main__':
    serv = MCServer(pp=False)
    print(f"Launching MC Listener Thread on Port: {serv.api_port}")
    serv.run()