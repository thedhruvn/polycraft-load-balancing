import unittest
import modules.comms.LobbyCommunicator as LobbyCom
from queue import Queue
import threading
import socket
import time


class MyTestCase(unittest.TestCase):
    def test_comms(self):
        in_queue = Queue()
        out_queue = Queue()
        lock = threading.Lock()
        tm_thread = LobbyCom.LobbyCommunicator(in_queue=in_queue,
                                      out_queue=out_queue,
                                      tm_lock=lock)

        tm_thread.start()
        expected_response = "Yo - this is a response"
        out_queue.put(expected_response)
        data = "test send"
        time.sleep(2)
        port = LobbyCom.PORT
        inPort = int(port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((LobbyCom.HOST, inPort))

            print("sending data to the server...")
            sock.sendall(bytes(data + "\n", "utf-8"))
            print("data sent!")
            received = str(sock.recv(1024), "utf-8")
            print(f"received data from the server: {received}")
            self.assertEqual(received, expected_response)

        tm_thread.kill()


if __name__ == '__main__':
    unittest.main()
