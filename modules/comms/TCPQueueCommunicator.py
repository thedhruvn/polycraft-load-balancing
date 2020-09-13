import threading
from modules.comms.TCPServers import *

PORT = 9007
HOST = "127.0.0.1"

"""
Thanks to the great dano: https://stackoverflow.com/questions/25245223/python-queue-queue-wont-work-in-threaded-tcp-stream-handler
Deets on socketserver: https://docs.python.org/3/library/socketserver.html

"""
class TCPQueueCommunicator(threading.Thread):

    def __init__(self, out_queue, in_queue, tm_lock, host=HOST, port=PORT, args=None, kwargs=None):
        threading.Thread.__init__(self, args, kwargs)
        self.out_queue = out_queue
        self.recv_queue = in_queue   # Queue contains msgs received.
        self.tm_lock = tm_lock
        self.server = None
        self.HOST = host
        self.PORT = port


    def kill(self):
        self.server.shutdown()

    def run(self):
        print(f"Initializing TCPServer on: {self.HOST}:{self.PORT}")

        self.server = ThreadedTCPLobbyServer((self.HOST, self.PORT),
                                             ThreadedTCPLobbyStreamHandler,
                                             in_queue=self.recv_queue,
                                             queue=self.out_queue)
        with self.server as server:
            server.serve_forever()


