from enum import Enum
import datetime
from mcstatus import MinecraftServer
from socket import timeout
import configparser
import socket
from functools import total_ordering
from modules.comms.LoadBalancerToMCMain import LBFormattedMsg
from main.MCServerMain import CommandSet as MCCommands
import os
from root import *
import threading

"""
Holds a server object and can run the main() function for the server object
"""
class Server:

    def __init__(self, ip, port, api_port, node_id, reattach = False, config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg')):
        self.ip = ip
        self.port = port
        self.api = api_port
        self.node_id = node_id
        self.config = configparser.ConfigParser()
        self.config.read(config)
        self.id = f"{self.ip}:{self.port}"
        self.teams = []
        self.players = []
        self.player_team = {}
        self.playercount = 0
        if not reattach:
            self.state = Server.State.INITIALIZING
        else:
            self.state = Server.State.STABLE
        self.last_request_time = None

        self.countfailures = 0
        self.maxFailsBeforeDown = 3
        self.mcServer = MinecraftServer(self.ip, self.port)

    def __hash__(self):
        return self.node_id.__hash__()

    def __lt__(self, other):
        if isinstance(other, Server):
            return self.playercount < other.playercount
            # if self.ip == other.ip:
            #     return self.port < other.port
            # else:
            #     return self.ip < other.ip
        else:
            raise ArithmeticError

    def __eq__(self, other):
        if isinstance(other, Server):
            return self.id == other.id
        elif isinstance(other, str):
            return self.id == other
        else:
            return False

    def eligible_for_new_teams(self):
        if self.state == Server.State.STABLE and len(self.teams) < int(self.config.get('SERVER', 'maxTeamsPerServer')):
            return True
        else:
            return False


    def is_ready(self):
        if self.state < Server.State.STABLE:
            return False
        return True

    def _is_mc_alive(self):
        #  Check to see if the server is up yet:
        # srv = MinecraftServer(self.ip, self.port)
        stat = ""
        try:
            stat = self.mcServer.status()
            if len(stat.raw) > 0:
                self.countfailures = 0
                return True
            # if (stat.raw['players']['online'] >= 0):
            #     self.countfailures = 0
            #     return True
                # Continue onwards and update the player lists!
        except timeout:
            # The Server is not up yet.
            print(f"[IsAlive]Server can't be accessed yet")
            self.countfailures += 1

        except KeyError:
            # The status return doesn't have a players or online segment
            print(f"Something weird with Status response: {stat.raw}")

        except ConnectionRefusedError:
            print(f"Err: Connection Refused? Is Alive {self.ip}:{self.port}")
            self.countfailures += 1

        except OSError:
            print(f"Err: OS Error - no response: {self.ip}:{self.port}")
            self.countfailures += 1

        except Exception as e:
            print(f"Err: Something else happened:{self.ip}:{self.port} \n {e}")
            self.countfailures += 1

        return False

    def _get_team_for_player(self, playerName):
        # TODO: implement REST API here.
        return -1


    def poll(self):
        print(f"{datetime.datetime.now()} Running Poll: {self.id}")
        if self.state == Server.State.INITIALIZING:
            #  Check to see if the server is up yet:
            if self._is_mc_alive():
                self.state = Server.State.STABLE
            elif self.countfailures > self.maxFailsBeforeDown*2:
                self.state = Server.State.CRASHED
            return

        if self.state == Server.State.STABLE or self.state == Server.State.WAITING_FOR_MERGE:
            # Check if the server is still up. Update the active player lists
            # srv = MinecraftServer(self.ip, self.port)
            stat = ""
            try:
                stat = self.mcServer.status(tries=10)

                self.playercount = stat.players.online
                playersdetected = {}
                if stat.players.sample is not None:
                    for player in stat.players.sample:
                        playersdetected.update({player.id: player.name})

                # Update player and team arrays
                self.player_team = {player: team for player, team in self.player_team.items() if player in playersdetected.keys()}

                if len(self.player_team) < len(playersdetected):
                    players_to_search = {player: name for player, name in playersdetected.items() if player not in self.player_team}
                    for player, name in players_to_search.items():
                        team = self._get_team_for_player(name)
                        self.player_team.update({player: team})


                self.players = list(self.player_team.keys())
                self.playercount = len(self.players)
                self.teams = list(set(self.player_team.values()))
                self.countfailures = 0

                self.check_is_server_api_alive()

                return

            except timeout:
                # The Server is not up yet.
                print(f"Error! Is Server Down?")
                self.countfailures += 1
                # self.state = Server.State.CRASHED

            except ConnectionRefusedError:
                print(f"Err: Connection Refused - state STABLE? {self.ip}:{self.port}")
                self.countfailures += 1
                # self.state = Server.State.CRASHED

            except KeyError:
                # The status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")
                # self.countfailures += 1

            except Exception as e:
                print(f"Something else went wrong... {e}")
                self.countfailures += 1

            if self.countfailures > self.maxFailsBeforeDown:
                self.state = Server.State.CRASHED
            return

        if self.state == Server.State.STABLE_BUT_TASK_FAILED:
            # Ping the API port to see if its back up!
            self.check_is_server_api_alive()

            stat = ""
            try:
                stat = self.mcServer.status()

                self.playercount = stat.players.online
                playersdetected = {}
                if stat.players.sample is not None:
                    for player in stat.players.sample:
                        playersdetected.update({player.id: player.name})

                # Update player and team arrays
                self.player_team = {player: team for player, team in self.player_team.items() if
                                    player in playersdetected.keys()}

                if len(self.player_team) < len(playersdetected):
                    players_to_search = {player: name for player, name in playersdetected.items() if
                                         player not in self.player_team}
                    for player, name in players_to_search.items():
                        team = self._get_team_for_player(name)
                        self.player_team.update({player: team})

                self.players = list(self.player_team.keys())
                self.playercount = len(self.players)
                self.teams = list(set(self.player_team.values()))
                self.countfailures = 0

                return

            except timeout:
                # The Server is not up yet.
                print(f"Error! Is Server Down?")
                self.countfailures += 1
                # self.state = Server.State.CRASHED
                # return
            except ConnectionRefusedError:
                print(f"Err: Connection Refused? - Stable failed task {self.ip}:{self.port}")
                self.countfailures += 1
                # self.state = Server.State.CRASHED
                # return False
            except KeyError:
                # The status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")

            except Exception as e:
                print(f"Something else went wrong... {e}")
                self.countfailures += 1
                # return

            if self.countfailures > self.maxFailsBeforeDown:
                self.state = Server.State.CRASHED
            return

        if self.state == Server.State.REQUESTED_DEACTIVATION:
            max_seconds_raw = self.config.get('SERVER', 'maxRequestProcessTime')
            max_seconds = int(max_seconds_raw) if max_seconds_raw and max_seconds_raw.isdecimal() else 600
            delta = datetime.timedelta(seconds=max_seconds)
            if delta < (datetime.datetime.now() - self.last_request_time):
                print("enough time has passed! We should now check to see if the server is behaving")
                self.state = Server.State.CONFIRMING_DEACTIVATION

            return

        if self.state == Server.State.CONFIRMING_DEACTIVATION:

            # srv = MinecraftServer(self.ip, self.port)
            stat = ""
            try:
                stat = self.mcServer.status()
                if stat.players.online > 0:
                    print(f"Error: Something went wrong with {self.id}. Should we re-send the request? {stat.raw}")
                    # TODO: Resend the deactivation request.
                    return
                else:
                    self.state = Server.State.DEACTIVATED       # No players online
            except timeout:
                # The Server is down
                print(f"Server {self.id} has been deactivated")
                self.state = Server.State.DEACTIVATED
                return
            except ConnectionRefusedError:
                print(f"Server {self.id} has been deactivated")
                self.state = Server.State.DEACTIVATED
                return
            except KeyError:
                # The server isn't down, but the status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")
                return
            except Exception as e:
                print(f"Something else went wrong: {e}")
                return

        if self.state == Server.State.CRASHED:
            print(f"This server is crashed! {self.id} - is it back up?")
            if self._is_mc_alive():
                self.state = Server.State.STABLE
            # TODO: Send msg to restart the server.
            return

        else:
            print(f"This server has been deactivated! Please don't run  me anymore!")
            return

    def check_is_server_api_alive(self):
        ## Ping the API port to confirm it is available!
        try:
            check_val = self.send_msg_to_server(LBFormattedMsg(MCCommands.HELLO))
            if check_val is not None and len(check_val) > 0:
                if self.state == Server.State.STABLE_BUT_TASK_FAILED:
                    print("yay! I'm back alive")
                    self.state = Server.State.STABLE

                return True

        except ConnectionRefusedError as e:
            if self.state == Server.State.STABLE:
                print("error - unable to connect to API. Please restart me!")
                self.state = Server.State.STABLE_BUT_TASK_FAILED
        except Exception as e:
            print("General Error")

        return False


    def add_player(self, playerUUID, teamID):
        # Send msg to server?
        # self.teams.append(teamID)
        # self.players.append(playerUUID)
        self.player_team.update({playerUUID: teamID})
        self.players = list(self.player_team.keys())
        self.teams = list(set(self.player_team.values()))
        self.playercount += 1

    def decommission(self, newServer =None):
        if self.state != Server.State.STABLE:      # Cannot call decommission on a transitioning server.
            return False
        if not self._is_mc_alive():
            self.state = Server.State.CRASHED
            return False

        if newServer is None and self.playercount > 0:
            return False

        if newServer is not None:
            newServer.state = Server.State.WAITING_FOR_MERGE
            self.state = Server.State.REQUESTED_DEACTIVATION
            self.last_request_time = datetime.datetime.now()
            print("Transitioning Players to a new server")
            msg = LBFormattedMsg(MCCommands.DEALLOCATE, f'{{"IP":"{newServer.ip}", "PORT":{newServer.port}}}')
            self.send_msg_threaded_to_server(msg)

            #  noTODO: send msg to server
        else:
            print("Decommissioning this server")
            self.state = Server.State.CONFIRMING_DEACTIVATION # No need to wait! Skip to the fun parts!
            self.last_request_time = datetime.datetime.now()
            msg = LBFormattedMsg(MCCommands.DEALLOCATE, "test Dealloc")
            self.send_msg_threaded_to_server(msg)
            #  noTODO: send msg to server

    def send_msg_threaded_to_server(self, msg: LBFormattedMsg):

        thread = threading.Thread(target=self.send_msg_to_server, args=(msg,))
        thread.setDaemon(True)
        thread.start()
        return True

    def send_msg_to_server(self, lb_fmt_msg: LBFormattedMsg):

        # self.socket = socket.create_connection(addr, timeout=timeout)
        #
        #
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.connect((self.ip, self.api))
            sock.settimeout(2)

            print("sending data to the server...")
            sock.sendall(bytes(lb_fmt_msg.msg + "\n", "utf-8"))
            print("data sent!")
            received = str(sock.recv(1024), "utf-8")
            print(f"received data from the server: {received}")
            return received
            # self.assertEqual(received, expected_response)

    @total_ordering
    class State(Enum):
        """
        Server State holder - prevents inadvertent re-requests to a server
        """
        INITIALIZING = -1               # Server has not yet started.
        STABLE = 0                      # No changes needed or all changes completed
        WAITING_FOR_MERGE = 1           # No new teams should enter this server because it is expecting a merge. Also, shouldn't get flagged for deallocation.
        REQUESTED_DEACTIVATION = 2      # A change has been requested & sent to the server
        CONFIRMING_DEACTIVATION = 3     # An appropriate amount of time has passed for the server to ack. and apply the change
        DEACTIVATED = 4                 # The server has acknowledged that the requested change is complete
        STABLE_BUT_TASK_FAILED = 91     # Edge case: can't connect to the Python API on a node.
        CRASHED = 99                    # Server is unexpectedly inaccessible.

        def __lt__(self, other):
            if self.__class__ is other.__class__:
                return self.value < other.value
            return NotImplemented

