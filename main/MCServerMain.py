from modules.comms import TCPServers
from modules.comms.TCPQueueCommunicator import TCPQueueCommunicator
import mcstatus
from queue import Queue, Empty
import threading
import sys
from enum import Enum
import subprocess
import configparser


class CommandSet(Enum):

    HELLO = 'hello'
    MCALIVE = 'mc_alive'
    MCSTATUS = 'mcstatus'
    LAUNCH = 'launch_mc'
    SHUTDOWN = 'kill'
    DEALLOCATE = 'stop'
    ABORT = 'abort'


class MCServer:

    def __init__(self,  config = '../configs/azurebatch.cfg'):
        self.mcport = 25565
        self.api_port = 9007
        self.comms = None
        self.in_queue = Queue()
        self.out_queue = Queue()
        self.minecraftserver = None

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


    def _launch_minecraft(self):
        self.minecraftserver = subprocess.Popen('./run_polycraft.sh oxygen', shell=True, cwd='scripts/', stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         bufsize=1,  # DN: 0606 Added for performance
                         universal_newlines=True,  # DN: 0606 Added for performance
                         )


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
                self.out_queue.put("Maybe!")

            elif CommandSet.MCSTATUS.value in next_line.lower():
                print("Testing: MCSTATUS")
                try:
                    serv = mcstatus.MinecraftServer.lookup("127.0.0.1:25565")
                    val = serv.status()
                    self.out_queue.put(val.raw)
                except Exception as e:
                    print("Err: Server is not up")
                    self.out_queue.put("Err: Server is not alive")


            else:
                print("unknown command")
                self.out_queue.put("Err: Unknown Command")

        self.comms.kill()
        self.comms.join(5)


if __name__ == '__main__':
    serv = MCServer()
    print(f"Launching MC Listener Thread on Port: {serv.api_port}")
    serv.run()