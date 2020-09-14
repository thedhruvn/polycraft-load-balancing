from modules.PoolManager import PoolManager
from modules.Server import Server
from modules.comms import TCPServers
from modules.comms.TCPQueueCommunicator import TCPQueueCommunicator
import queue
import threading
import time
import sys
from enum import Enum
import json
from json import JSONDecodeError
import datetime
from root import *

class CommandSet(Enum):

    HELLO = 'hello'
    SERVERFORPLAYER = 'get_server_for_player'
    SERVERFORTEAM = 'get_server_for_team'
    SHUTDOWN = 'kill'
    ADDNEW = 'add_one_server'
    REMOVE = 'remove_one_server'



class LoadBalancerMain:

    def __init__(self, config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg'), credentials=os.path.join(ROOT_DIR, 'configs/SECRET_paleast_credentials.cfg')):
        self.pool = PoolManager(config=config)
        self.config = self.pool.config
        self.lobbyThread = None
        self.lobbyPort = int(self.config.get('POOL', 'lobby_port'))
        self.msgs_from_lobby = queue.Queue()
        self.replies_to_lobby = queue.Queue()
        self.state = LoadBalancerMain.State.STARTING
        self.target_deallocation_server = None

    def _launch_lobby_thread(self):
        # in_queue = Queue()
        # out_queue = Queue()
        lock = threading.Lock()
        self.lobbyThread = TCPQueueCommunicator(in_queue=self.msgs_from_lobby,
                                                out_queue=self.replies_to_lobby,
                                                tm_lock=lock,
                                                port=self.lobbyPort)
        self.lobbyThread.start()
        print(f"Lobby thread launched: {self.lobbyPort}")

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
            next_line = self.msgs_from_lobby.get(False, timeout=0.025)
            print(f"input: {next_line}")
            # self.PAL_log.message_strip(str(next_line))
            sys.stdout.flush()
            sys.stderr.flush()
        except queue.Empty:
            pass

        return str(next_line, TCPServers.ENCODING)

    def _serverResponseBuilder(self, server: Server = None, msg: str = ""):
        if server is None:
            return '{"IP":"None", "PORT":0, "MSG": "' + msg + '"}'
        val = f'"IP":"{server.ip}", "PORT":{server.port}, "MSG": "{msg}"'
        print('server Response: {' + val + '}\n')
        return '{' + val + '}\n'

    def main(self):

        # Deinitialization Case:
        waiting_for_server_to_kick_players = True

        # Flag - joining an existing server or reconnecting to a new one?
        is_new_pool = True

        max_retry_initialize = 5
        id = self.config.get('POOL', 'id')
        is_new_pool = self.pool.initializeManager(id)
        counter = 0
        initialized = self.pool.check_is_pool_steady()
        while not initialized and counter < max_retry_initialize:
            print("waiting for initialization...")
            time.sleep(60)
            counter += 1
            initialized = self.pool.check_is_pool_steady()

        should_continue = counter < max_retry_initialize

        if should_continue:
            self.pool.update_server_list()
            self._launch_lobby_thread()

        ct = 0

        while should_continue:
            # Case 1: Waiting for the MC Servers to spin up on each Node
            if self.state == LoadBalancerMain.State.STARTING:

                next_line = self._check_queues().lower()
                if next_line is None or next_line == '':
                    pass

                else:
                    print("MC Servers are not up yet.")
                    self.replies_to_lobby.put("Err: MC Servers are not up yet.")

                if datetime.datetime.now().second % 30 == 0:
                    print(f"attempt: {ct} - are MC servers online?")
                    ct += 1
                    all_ready = True
                    for server in self.pool.servers:
                        server.poll()
                        if server.state < Server.State.STABLE:
                            all_ready = False
                    if all_ready:
                        self.state = LoadBalancerMain.State.STABLE
                        print("Servers Online!")

            #  Case 2: All Servers are stable - we can begin handling commands sent to us from the Polycraft Lobby
            else:
                next_line = self._check_queues().lower()
                if next_line is None or next_line == '':
                    pass

                elif CommandSet.HELLO.value in next_line:
                    print("SUCCESS")
                    self.replies_to_lobby.put("SUCCESS")

                elif CommandSet.SERVERFORTEAM.value in next_line:
                    try:
                        command = json.loads(next_line)
                        id = command['playeruuid']
                        team = command['playerteam']
                        server = self.pool.getServerForTeam(team)
                        server.add_player(id, team)
                        self.replies_to_lobby.put(self._serverResponseBuilder(server))

                        # TODO: Should i remove these?
                        for server in self.pool.servers:
                            server.poll()
                    except JSONDecodeError as e:
                        print(f"Error! BAD Json From Minecraft {e}")
                        self.replies_to_lobby.put(self._serverResponseBuilder(None))
                    except TypeError as e:
                        print(f"Error! Type Error in Json Response: {e}")
                        self.replies_to_lobby.put(self._serverResponseBuilder(None, "Error! Bad Input"))
                    except Exception as e:
                        print(f"Error! Unknown Problem {e}")
                        self.replies_to_lobby.put(self._serverResponseBuilder(None, "Error! Unknown Problem"))

                elif CommandSet.ADDNEW.value in next_line:
                    print(f"Adding one server to the pool")
                    if self.__add_server():
                        self.replies_to_lobby.put("Adding new server!")
                    else:
                        self.replies_to_lobby.put("Error - unable to add new server")

                elif CommandSet.REMOVE.value in next_line:
                    print(f"Removing One Server")
                    if self.__find_and_remove_server():
                        self.replies_to_lobby.put(f"Deallocating a server! {self.target_deallocation_server.id}")
                    else:
                        self.replies_to_lobby.put("Error - unable to remove a server")

                else:
                    print(f"Error! Unknown command!")
                    self.replies_to_lobby.put(self._serverResponseBuilder(None, "Error! Unknown Command"))

                # Case 2a:  No Changes have been requested of the Pool. Run the Load Balancing Algorithms
                #           to see if any servers need to be spun up or killed.
                if self.state == LoadBalancerMain.State.STABLE:

                    if datetime.datetime.now().second % int(self.config.get('LOAD', 'secondsBetweenMCPoll')):
                        for server in self.pool.servers:
                            server.poll()

                        if self.pool.check_is_pool_steady() and not self.pool.flag_transition:
                            self.should_add_server_check()
                            self.should_merge_servers_check()

                # Case 2b:  Request has been made for the Pool to increase in size. Poll to see if this has changed.
                #           detect when the new server has MC up and running and shift back to STABLE after that.
                elif self.state == LoadBalancerMain.State.INCREASING:
                    initialized = self.pool.check_is_pool_steady(id)
                    all_ready = False
                    if initialized:
                        all_ready = True
                        self.pool.update_server_list(id)

                    if datetime.datetime.now().second % int(self.config.get('LOAD', 'secondsBetweenMCPoll')):
                        for server in self.pool.servers:
                            server.poll()
                            if server.state < Server.State.STABLE:
                                all_ready = False
                        if all_ready:
                            self.state = LoadBalancerMain.State.STABLE
                            self.pool.flag_transition = False
                            self.pool.update_server_list()  # TODO: Figure out when to call this.

                # Case 2c:  Load Balancer has requested a decrease in Nodes.
                #           Detect if the decrease is happening or not.
                elif self.state == LoadBalancerMain.State.DECREASING:
                    # Case 1: Waiting for a server to get de-initialized
                    if waiting_for_server_to_kick_players and self.target_deallocation_server is not None:

                        if datetime.datetime.now().second % int(self.config.get('LOAD', 'secondsBetweenMCPoll')):
                            # all_ready = False
                            for server in self.pool.servers:
                                server.poll()
                                # if server.state == Server.State.DEACTIVATED:
                                #     all_ready = True
                        if self.target_deallocation_server.state == Server.State.DEACTIVATED:
                            waiting_for_server_to_kick_players = False

                    # Case 2: Remove node from pool
                    else:
                        if self.target_deallocation_server is not None:
                            if self.pool.actual_remove_server(self.target_deallocation_server):
                                self.pool.update_server_list()
                                self.state = LoadBalancerMain.State.STABLE
                                self.target_deallocation_server = None
                                waiting_for_server_to_kick_players = True



    class State(Enum):
        STARTING = -1
        STABLE = 0
        DECREASING = 1
        INCREASING = 2

    def should_add_server_check(self):
        pass

    def should_merge_servers_check(self):
        pass

    def __add_server(self):
        if not self.pool.flag_transition and self.pool.check_is_pool_steady():
            if self.pool.expand_pool_add_server(1):
                self.state = LoadBalancerMain.State.INCREASING
                return True
        return False

    def __find_and_remove_server(self):
        list_of_empty_servers =[]
        for server in self.pool.servers:
            server.poll()

        list_of_empty_servers = [srv for srv in self.pool.servers if srv.playercount == 0]

        # Case A: we can try to remove an empty server
        if len(list_of_empty_servers) > 0:
            if self.pool.signal_remove_server(list_of_empty_servers[0]):
                self.target_deallocation_server = list_of_empty_servers[0]
                self.state = LoadBalancerMain.State.DECREASING
                return True

        # Case B: We need to merge two servers together - pick the least two filled and merge the smaller with the larger
        # Sort our server pool by playercount:
        self.pool.servers.sort()

        # merge [0] with [1]
        if len(self.pool.servers) > 1:
            # TODO: check to see if [1] has room
            if self.pool.signal_remove_server(self.pool.servers[0], self.pool.servers[1]):
                self.target_deallocation_server = self.pool.servers[0]
                self.state = LoadBalancerMain.State.DECREASING
                return True

        return False