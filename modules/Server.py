from enum import Enum
import datetime
from mcstatus import MinecraftServer
from socket import timeout
import configparser

"""
Holds a server object and can run the main() function for the server object
"""
class Server:

    def __init__(self, ip, port, api_port, config = '../configs/azurebatch.cfg'):
        self.ip = ip
        self.port = port
        self.api = api_port
        self.config = configparser.ConfigParser()
        self.config.read(config)
        self.id = f"{self.ip}:{self.port}"
        self.teams = []
        self.players = []
        self.playercount = 0
        self.state = Server.State.INITIALIZING
        self.last_request_time = None

    def __hash__(self):
        return self.id.__hash__()

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

    def poll(self):
        if self.state == Server.State.INITIALIZING:
            #  Check to see if the server is up yet:
            srv = MinecraftServer(self.ip, self.port)
            stat = ""
            try:
                stat = srv.status()
                if(stat.raw['players']['online'] == 0):
                    self.state = Server.State.STABLE
                    return
            except timeout:
                # The Server is not up yet.
                print(f"Server can't be accessed yet")
                return
            except KeyError:
                # The status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")
                return

        elif self.state == Server.State.STABLE:
            # TODO: What do I do now?
            return

        elif self.state == Server.State.REQUESTED_DEACTIVATION:
            max_seconds_raw = self.config.get('SERVER', 'maxRequestProcessTime')
            max_seconds = int(max_seconds_raw) if max_seconds_raw and max_seconds_raw.isdecimal() else 600
            delta = datetime.timedelta(seconds=max_seconds)
            if delta < (datetime.datetime.now() - self.last_request_time):
                print("enough time has passed! We should now check to see if the server is behaving")
                self.state = Server.State.CONFIRMING_DEACTIVATION

            return

        elif self.state == Server.State.CONFIRMING_DEACTIVATION:

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
            except KeyError:
                # The server isn't down, but the status return doesn't have a players or online segment
                print(f"Something weird with Status response: {stat.raw}")
                return

        else:
            print(f"This server has been deactivated! Please don't run  me anymore!")
            return

    def add_player(self, playername, teamID):
        # Send msg to server?
        self.teams.append(teamID)
        self.players.append(playername)
        self.playercount += 1

    def decommission(self, newServer=None):

        if self.state != Server.State.STABLE:      # Cannot call decommission on a transitioning server.
            return False


        if newServer is not None:
            print("Transitioning Players to a new server")
            #  TODO: send msg to server
        else:
            print("Decommissioning this server")
            #  TODO: send msg to server

        self.state = Server.State.REQUESTED_DEACTIVATION
        self.last_request_time = datetime.datetime.now()

    class State(Enum):
        """
        Server State holder - prevents inadvertent re-requests to a server
        """
        INITIALIZING = -1           # Server has not yet started.
        STABLE = 0                  # No changes needed or all changes completed
        REQUESTED_DEACTIVATION = 1        # A change has been requested & sent to the server
        CONFIRMING_DEACTIVATION = 2     # An appropriate amount of time has passed for the server to ack. and apply the change
        DEACTIVATED = 3            # The server has acknowledged that the requested change is complete

