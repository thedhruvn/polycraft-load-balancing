from modules.PoolManager import PoolManager
from modules.Server import Server
from modules.comms import TCPServers
from modules.comms.TCPQueueCommunicator import TCPQueueCommunicator
from modules.comms.LoadBalancerToMCMain import LBFormattedMsg
import queue
import threading
import time
import sys
from enum import Enum
import json
from json import JSONDecodeError
import datetime
from root import *
import re
from main.MCServerMain import CommandSet as MCCommands


class CommandSet(Enum):
    HELLO = 'hello'
    SERVERFORPLAYER = 'get_server_for_player'
    SERVERFORTEAM = 'get_server_for_team'
    SHUTDOWN = 'kill'
    ADDNEW = 'add_one_server'
    REMOVE = 'remove_one_server'
    LISTSERVERS = 'list_all'
    QUERYMC = 'poll_mc'
    STATE = "status"


class LoadBalancerMain:

    def __init__(self, config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg'),
                 credentials=os.path.join(ROOT_DIR, 'configs/SECRET_paleast_credentials.cfg')):
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

        return str(next_line, TCPServers.ENCODING, 'ignore')

    def _serverResponseBuilder(self, server: Server = None, msg: str = ""):
        if server is None:
            return '{"IP":"None", "PORT":0, "MSG": "' + msg + '"}'
        val = f'"IP":"{server.ip}", "PORT":{server.port}, "MSG": "{msg}"'
        print('server Response: {' + val + '}\n')
        return '{' + val + '}\n'

    def main(self):

        max_retry_initialize = 5
        id = self.config.get('POOL', 'id')
        is_new_pool = self.pool.initializeManager(id)
        counter = 0
        self.pool.poll_servers_and_update()
        initialized = self.pool.check_is_pool_steady()
        while not initialized and counter < max_retry_initialize:
            if is_new_pool:
                print("waiting for initialization...")
            else:
                print("Existing Pool Detected. Reconnecting to: " + id)
            time.sleep(60)
            counter += 1
            self.pool.poll_servers_and_update()
            initialized = self.pool.check_is_pool_steady()

        should_continue = counter < max_retry_initialize

        if should_continue:
            self.pool.update_server_list()
            self._launch_lobby_thread()

        ct = 0
        seconds_ticker = 1
        modifier = 0

        while should_continue:

            seconds_ticker = datetime.datetime.now().second

            # Case A: Waiting for the MC Servers to spin up on each Node
            if self.state == LoadBalancerMain.State.STARTING:

                next_line = self._check_queues().lower()
                if next_line is None or next_line == '':
                    pass

                else:
                    print("Load Balancer Still Initializing.")
                    self.replies_to_lobby.put("Err: Load Balancer Connecting to Servers.")

                if self.poll_servers(seconds_ticker, modifier):
                    print(f"attempt: {ct} - are MC servers online?")
                    ct += 1
                    all_ready = self.pool.check_is_pool_steady()    # Ensure that the pool is stable, too!
                    for server in self.pool.servers:
                        if server.state < Server.State.STABLE:
                            all_ready = False
                    if all_ready:
                        self.state = LoadBalancerMain.State.STABLE
                        print("Servers Online!")

            #  Case B: All Servers are stable - we can begin handling commands sent to us from the Polycraft Lobby
            else:

                # Check for Commands sent to the Listener port
                next_line = self._check_queues().lower()
                if next_line is None or next_line == '':
                    pass

                elif CommandSet.STATE.value in next_line:
                    print("requested status...")
                    self.replies_to_lobby.put(f"State: {self.state.name}")

                elif CommandSet.HELLO.value in next_line:
                    print("SUCCESS")
                    self.replies_to_lobby.put("SUCCESS")

                # Debug #
                elif CommandSet.QUERYMC.value in next_line:
                    print("sending msg to MCServer...")
                    valid = False
                    for server in self.pool.servers:
                        if str(server.port) in next_line:
                            msg = re.sub(rf"{CommandSet.QUERYMC.value}|{server.port}", "", next_line).strip()
                            msg = LBFormattedMsg(MCCommands.PASSMSG, msg)
                            server.send_msg_threaded_to_server(msg)
                            self.replies_to_lobby.put("Sent to Server!")
                            valid = True
                            break

                    if not valid:
                        self.replies_to_lobby.put("Err: Invalid Server addr.")

                # Debug #
                elif CommandSet.LISTSERVERS.value in next_line:
                    print("Listing all servers")
                    result = "{"
                    for server in self.pool.servers:
                        result += f'"{server.id}":{{"api_port":{server.api}, "players":{server.playercount}, "state":"{server.state.name}"}},'
                    for team, server in self.pool.teams_to_servers.items():
                        result += f'"team_map":{{"{team}":"{server.id}"}},'
                    result += "}"
                    self.replies_to_lobby.put(result)

                elif CommandSet.SERVERFORTEAM.value in next_line:
                    try:
                        command = json.loads(next_line)
                        uid = command['playeruuid']
                        team = command['playerteam']
                        server = self.pool.getServerForTeam(team)
                        server.add_player(uid, team)
                        self.replies_to_lobby.put(self._serverResponseBuilder(server))
                        modifier += 1  # TODO: does this modifier crap even work? Should we add a skip counter instead?
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

                modifier = self.handle_active_state(seconds_ticker, modifier)

    def poll_servers(self, seconds_ticker, modifier=0):
        """
        Periodically poll servers and update the PoolManager state
        :param seconds_ticker: current seconds
        :param modifier: iterations of polling to skip
        :return: True if the servers were polled and updated this tick.
        """

        if (seconds_ticker % int(self.config.get('LOAD', 'secondsBetweenMCPoll'))) == 0:
            if modifier > 0:
                modifier -= 1
                return False
            self.pool.poll_servers_and_update()
            return True
        return False

    def handle_active_state(self, seconds_ticker, modifier):

        if self.poll_servers(seconds_ticker, modifier):

            # state = STABLE - check all nodes and see if any crashed
            if self.state == LoadBalancerMain.State.STABLE:
                crashList = []          # Cases where the server itself crashed
                restartAPIlist = []     # Cases where the mainTask ended

                for server in self.pool.servers:
                    #         server.poll()
                    if server.state == Server.State.CRASHED:
                        crashList.append(server)
                    if server.state == Server.State.STABLE_BUT_TASK_FAILED:
                        restartAPIlist.append(server)

                if len(crashList) > 0:
                    pass    # TODO: Confirm that the pool's state changes to TRANSITIONING
                    # self.pool.flag_transition = True
                for server in crashList:
                    self.__remove_specific_server(server)

                for server in restartAPIlist:
                    self.pool.batchclient.add_task_to_start_server()
                    self.state = LoadBalancerMain.State.RESTARTING_TASK

                if self.pool.check_is_pool_steady(): # and not self.pool.flag_transition:
                    self.should_add_server_check()
                    self.should_merge_servers_check()

            # state = RESTARTING_TASK   - a new tasks need to be added to the pool. Don't allow auto-balancing here.
            elif self.state == LoadBalancerMain.State.RESTARTING_TASK:
                # if self.poll_servers(seconds_ticker, modifier):
                all_nodes_stable = True
                # Continue monitoring for crashes
                crashList = []
                for server in self.pool.servers:
                    if server.state == Server.State.CRASHED:
                        crashList.append(server)
                    if server.state == Server.State.STABLE_BUT_TASK_FAILED:
                        all_nodes_stable = False

                if all_nodes_stable:
                    self.state = LoadBalancerMain.State.STABLE

                for server in crashList:
                    self.__remove_specific_server(server)   # TODO: Confirm that the pool changes its state.

            # Case 3:   Request has been made for the Pool to increase in size. Poll to see if this has changed.
            #           detect when the new server has MC up and running and shift back to STABLE after that.
            elif self.state == LoadBalancerMain.State.INCREASING:
                # if self.poll_servers(seconds_ticker, modifier):
                initialized = self.pool.check_is_pool_steady()
                if initialized:
                    self.pool.update_server_list()
                    self.state = LoadBalancerMain.State.WAITING_FOR_NEW_SERVERS
                    # print("State Changed")
                    # return
                    # self.state = LoadBalancerMain.State.WAITING_FOR_NEW_SERVERS

            # Case 3a:      The Pool is Steady, but the MC Server hasn't started yet. Poll occasionally until
            #               its online!
            elif self.state == LoadBalancerMain.State.WAITING_FOR_NEW_SERVERS:
                all_ready = True
                for server in self.pool.servers:
                    if server.state < Server.State.STABLE:
                        all_ready = False
                if all_ready:
                    self.state = LoadBalancerMain.State.STABLE
                    # self.pool.flag_transition = False
                    self.pool.update_server_list()

            # Case 4:   Load Balancer has requested a decrease in Nodes.
            #           Detect if the decrease is happening or not.
            elif self.state == LoadBalancerMain.State.DECREASING:
                # Case 1: Waiting for a server to get de-initialized
                if self.target_deallocation_server is not None:
                    # if self.poll_servers(seconds_ticker, modifier):
                    if self.target_deallocation_server.state == Server.State.DEACTIVATED:
                        self.state = LoadBalancerMain.State.TRIGGER_REMOVAL
                else:
                    raise Exception("Hmm... How'd I get here?")

            # Case 4a:  Manual Removal or Crash will automatically switch State to here
            #           Or this comes after the autobalanced server has moved players out of its server
            elif self.state == LoadBalancerMain.State.TRIGGER_REMOVAL:
                if self.target_deallocation_server is not None:
                    if self.pool.actual_remove_server(self.target_deallocation_server):
                        # self.pool.update_server_list()
                        self.state = LoadBalancerMain.State.WAIT_FOR_REMOVAL
                        self.target_deallocation_server = None
                        modifier += 2

            # Case 5:   Remove node from pool - the server has shut down - wait for Pool to Stabilize.
            #           #TODO: Should the pool be allowed to also increase? Probably not. Also, wait to handle crashes.
            elif self.state == LoadBalancerMain.State.WAIT_FOR_REMOVAL:
                # else:   # Case 3 - crash triggered emergency removal
                # if self.poll_servers(seconds_ticker, modifier):
                if self.pool.check_is_pool_steady():
                    self.pool.update_server_list()
                    self.state = LoadBalancerMain.State.STABLE

            return modifier

    class State(Enum):
        STARTING = -2
        WAIT_FOR_BOOT = -1
        STABLE = 0
        RESTARTING_TASK = 1
        DECREASING = 2
        TRIGGER_REMOVAL = 3
        WAIT_FOR_REMOVAL = 4
        INCREASING = 5
        WAITING_FOR_NEW_SERVERS = 6

    def should_add_server_check(self):
        pass

    def should_merge_servers_check(self):
        pass

    def __add_server(self):
        if self.pool.check_is_pool_steady() and self.state in [LoadBalancerMain.State.STABLE, LoadBalancerMain.State.RESTARTING_TASK]:
            if self.pool.expand_pool_add_server(1):                 # CONFIRMED: this changes the pool.allocation_state
                self.state = LoadBalancerMain.State.INCREASING
                # self.pool.poll_servers_and_update()
                return True
        return False

    def __remove_specific_server(self, server):

        if self.pool.actual_remove_server(server):
            self.state = LoadBalancerMain.State.WAIT_FOR_REMOVAL
            self.pool.update_server_list()

    def __find_and_remove_server(self):
        """
        Load Balancer Auto-trigger to remove a node. Can also be manually fired.
        :return: False if a pool cannot be removed right now.
        """
        # self.pool.poll_servers_and_update()
        if self.state not in [LoadBalancerMain.State.STABLE, LoadBalancerMain.State.RESTARTING_TASK]:
            print("Err: LoadBalancer is not in a steady state for removal.")
            return False

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


if __name__ == '__main__':
    lb = LoadBalancerMain()
    lb.main()
