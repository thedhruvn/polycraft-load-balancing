import threading

import psutil

from modules.comms.TCPServers import *
from misc.ColorLogBase import ColorLogBase
from psutil import process_iter
from signal import SIGTERM
PORT = 9007
HOST = "0.0.0.0"

"""
Thanks to the great dano: https://stackoverflow.com/questions/25245223/python-queue-queue-wont-work-in-threaded-tcp-stream-handler
Deets on socketserver: https://docs.python.org/3/library/socketserver.html

"""
class TCPQueueCommunicator(threading.Thread, ColorLogBase):

    def __init__(self, out_queue, in_queue, tm_lock, host=HOST, port=PORT, args=None, kwargs=None):
        threading.Thread.__init__(self, args, kwargs)
        ColorLogBase.__init__(self)
        self.out_queue = out_queue
        self.recv_queue = in_queue   # Queue contains msgs received.
        self.tm_lock = tm_lock
        self.server = None
        self.HOST = host
        self.PORT = port


    def kill(self):
        self.server.shutdown()

    def clear_other_processes(self):
        self.log.info("Attempting to force-clear other ports...")
        bflag = False
        try:
            for proc in process_iter():
                for conns in proc.connections(kind='inet'):
                    if conns.laddr.port == self.PORT:
                        self.log.warning(f"Killing process {proc} to clear port: {self.PORT}")
                        proc.send_signal(SIGTERM)
                        bflag = True
        except psutil.AccessDenied as e:
            self.log.warning(f"Error - unable to force-close other processes. {e}")
            return
        except Exception as e:
            self.log.error(f"Error - unknown exception occurred: {e}")
            return
        if not bflag:
            self.log.info(f"No other processes on {self.PORT} detected.")

    def run(self):
        self.log.info(f"Initializing TCPServer on: {self.HOST}:{self.PORT}")

        # Force-remove other running processes on this port, just in case.
        # https://stackoverflow.com/questions/20691258/
        self.clear_other_processes()

        self.server = ThreadedTCPLobbyServer((self.HOST, self.PORT),
                                             ThreadedTCPLobbyStreamHandler,
                                             bind_and_activate=False,               # Manually activate this one.
                                             in_queue=self.recv_queue,
                                             queue=self.out_queue)

        # Sets the ability to reuse a port if it's closed: https://www.py4u.net/discuss/12199
        self.server.activate()

        with self.server as server:
            server.serve_forever()


