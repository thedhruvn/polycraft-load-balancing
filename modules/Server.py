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
        srv = MinecraftServer(self.ip, self.port)
        stat = ""
        try:
            stat = srv.status()
            if (stat.raw['players']['online'] >= 0):
                return True
                # Continue onwards and update the player lists!
        except timeout:
            # The Server is not up yet.
            print(f"[IsAlive]Server can't be accessed yet")
            return False
        except KeyError:
            # The status return doesn't have a players or online segment
            print(f"Something weird with Status response: {stat.raw}")
            return False
        except ConnectionRefusedError:
            print(f"Err: Connection Refused? {self.ip}:{self.port}")
            return False
        except OSError:
            print(f"Err: OS Error - no response: {self.ip}:{self.port}")
            return False
        except Exception as e:
            print(f"Err: Something else happened:{self.ip}:{self.port} \n {e}")
            return False

    def _get_team_for_player(self, playerName):
        # TODO: implement REST API here.
        return -1


    def poll(self):
        if self.state == Server.State.INITIALIZING:
            #  Check to see if the server is up yet:
            if self._is_mc_alive():
                self.state = Server.State.STABLE
            else:
                return

        if self.state == Server.State.STABLE or self.state == Server.State.WAITING_FOR_MERGE:
            # Check if the server is still up. Update the active player lists
            srv = MinecraftServer(self.ip, self.port)
            stat = ""
            try:
                stat = srv.status()

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
                return

            except timeout:
                # The Server is not up yet.
                print(f"Error! Is Server Down?")
                self.state = Server.State.CRASHED
                return
            except ConnectionRefusedError:
                print(f"Err: Connection Refused? {self.ip}:{self.port}")
                self.state = Server.State.CRASHED
                return False
            except KeyError:
                # The status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")
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

            srv = MinecraftServer(self.ip, self.port)
            stat = ""
            try:
                stat = srv.status()
                if (stat.raw['players']['online'] > 0):
                    print(f"Error: Something went wrong with {self.id}. Should we re-send the request? {stat.raw}")
                    # TODO: Resend the deactivation request.
                    return
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

        if self.state == Server.State.CRASHED:
            print(f"This server is crashed! {self.id} - is it back up?")
            if self._is_mc_alive():
                self.state = Server.State.STABLE
            # TODO: Send msg to restart the server.
            return

        else:
            print(f"This server has been deactivated! Please don't run  me anymore!")
            return

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
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.ip, self.api))

            print("sending data to the server...")
            sock.sendall(bytes(lb_fmt_msg.msg + "\n", "utf-8"))
            print("data sent!")
            received = str(sock.recv(1024), "utf-8")
            print(f"received data from the server: {received}")
            # self.assertEqual(received, expected_response)

    @total_ordering
    class State(Enum):
        """
        Server State holder - prevents inadvertent re-requests to a server
        """
        INITIALIZING = -1           # Server has not yet started.
        STABLE = 0                  # No changes needed or all changes completed
        WAITING_FOR_MERGE = 5           # No new teams should enter this server because it is expecting a merge. Also, shouldn't get flagged for deallocation.
        REQUESTED_DEACTIVATION = 1        # A change has been requested & sent to the server
        CONFIRMING_DEACTIVATION = 2     # An appropriate amount of time has passed for the server to ack. and apply the change
        DEACTIVATED = 3            # The server has acknowledged that the requested change is complete
        CRASHED = 4                 # Server is unexpectedly inaccessible.

        def __lt__(self, other):
            if self.__class__ is other.__class__:
                return self.value < other.value
            return NotImplemented

