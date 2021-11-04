import sys
import socketserver
from socketserver import TCPServer
import queue
import threading
from misc.ColorLogBase import ColorLogBase

ENCODING = 'utf-8'


class ThreadedTCPLobbyServer(TCPServer, ColorLogBase):
    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True,
                 queue=None, in_queue=None):
        ColorLogBase.__init__(self)
        self.out_queue = queue
        self.in_queue = in_queue
        TCPServer.__init__(self, server_address, RequestHandlerClass,
                           bind_and_activate=bind_and_activate)

    def activate(self):
        self.allow_reuse_address = True
        try:
            self.server_bind()
            self.server_activate()
        except:
            self.server_close()
            raise


class ThreadedTCPLobbyStreamHandler(socketserver.StreamRequestHandler, ColorLogBase):
    def __init__(self, request, client_address, server: ThreadedTCPLobbyServer):
        """
        Each StreamHandler is created on the fly whenever a message
        is received by the server module. Pass the server queues
        to this object in its constructor.
        :param request: socket
        :param client_address: ip address of the sender
        :param server: the Server reference to get the queues from.
        """
        ColorLogBase.__init__(self)
        self.out_queue = server.out_queue
        self.in_queue = server.in_queue
        socketserver.StreamRequestHandler.__init__(self, request, client_address, server)

    def handle(self):
        """
        Handler function operates using a Queue to pass message to the main thread
        and send the correct response to send back to the sender
        The queue is unchecked - if more than one sender will exist, include the client_address in the queue

        NOTE: inbound message MUST INCLUDE THE '\n' as the msg terminator,
        as we use #readline() to process Stream messages.

        """
        command_from_lobby = self.rfile.readline().strip()
        if not command_from_lobby:
            return

        cur_thread = threading.current_thread()
        self.log.debug(f"{cur_thread}: msg received: {command_from_lobby}")
        self.in_queue.put(command_from_lobby)
        self.process_response()
        self.finish()

    def process_response(self):
        """
        Wait for a response from the main thread to appear in the outbound queue. Send that message to the msg. sender.

        UPDATE 9.25 - setting a timeout to allow for the server to close gracefully when necessary.

        :return:
        """
        sent_response = False
        max_time = 1440  # max timeout in seconds
        while not sent_response:
            try:
                # response_to_lobby = self.out_queue.get(True)
                response_to_lobby = self.out_queue.get(True, timeout=max_time)
                sys.stdout.flush()
                sys.stderr.flush()
                response = bytes(response_to_lobby, ENCODING)
                self.request.sendall(response)
                sent_response = True
            except queue.Empty:
                self.log.error(f"Main thread took more than {max_time} to process. Please re-send command.")
                response = bytes("ERROR", ENCODING)
                self.request.sendall(response)
                sent_response = True

