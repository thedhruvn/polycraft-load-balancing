import configparser

from azure.batch.models import BatchErrorException

from modules.BatchPool import BatchPool
from modules.Server import Server
import time
import queue
import threading
from modules.comms.TCPQueueCommunicator import TCPQueueCommunicator


class PoolManager:

    def __init__(self, config = '../configs/azurebatch.cfg'):
        self.config = configparser.ConfigParser()
        self.config.read(config)
        self.raw_config_file = config

        # self.state = PoolManager.State(0, {})
        self.servercount = 0
        self.teams_to_servers = {}
        self.servers = []
        self.player_to_team_lookup = {}
        self.player_to_server_lookup = {}

        self.flag_transition = False        # Set to true during expansions OR contractions to prevent multiple triggers
        self.batchclient = None

    def check_is_pool_steady(self, pool_id=None):

        if pool_id is None:
            if self.batchclient:
                pool_id = self.batchclient.pool_id
            else:
                return False
        try:
            pool = self.batchclient.client.pool.get(pool_id)
            if pool is not None and 'steady' in pool.allocation_state.value:
                return True
            return False
        except BatchErrorException as e:
            return False
        except Exception as e:
            return False

    def update_server_list(self, pool_id=None):

        # pool = self.batchclient.client.pool.get(pool_id)
        if pool_id is None:
            if self.batchclient:
                pool_id = self.batchclient.pool_id
            else:
                return False


        if self.check_is_pool_steady(pool_id):
            self.servers.clear()
            self.servercount = 0
            for node in self.batchclient.client.compute_node.list(pool_id):
                ip = None
                minecraftPort = None
                APIPort = None

                for endpoint in node.endpoint_configuration.inbound_endpoints:
                    if 'minecraft' in endpoint.name:
                        minecraftPort = endpoint.frontend_port
                        ip = endpoint.public_ip_address
                    if 'api' in endpoint.name:
                        APIPort = endpoint.frontend_port
                        ip = endpoint.public_ip_address

                newSrv = Server(ip=ip, port=minecraftPort, api_port=APIPort)
                newSrv.poll()   #  Update its state
                self.add_logical_server(newSrv)
            return True
        return False

    def initializeManager(self, pool_id = None):
        self.batchclient = BatchPool(config=self.raw_config_file)
        if pool_id is None:
            pool_id = self.config.get('POOL', 'id')
        existing_pool = self.batchclient.check_or_create_pool(pool_id)
        if existing_pool is None:
            return True     # This should be the case for a newly created pool

        return False

    def expand_pool_add_server(self, count):
        """
        Attempt to expand the batch pool by a countable number of nodes
        Checks to see if the pool's allocation state is Steady before attempting to expand
        :param count: number of nodes to add (must be positive)
        :return: True if the pool's resize was successfully submitted to Azure
        """
        if count > 0 and self.batchclient is not None:
            pool = self.batchclient.check_or_create_pool(self.batchclient.pool_id)
            count += len(self.servers)
            if pool is not None and 'steady' in pool.allocation_state.value and not self.flag_transition:
                if self.batchclient.expand_pool(count):
                    self.flag_transition = True
                    return True

        # TODO:
        return False

    def actual_remove_server(self, server: Server):
        if self.check_is_pool_steady() and self.flag_transition:
            if server.state == Server.State.DEACTIVATED:
                if self.batchclient.remove_node_from_pool(server.node_id):
                    self.flag_transition = False
                    self.servers.remove(server)
                    return True
        return False

    def signal_remove_server(self, server: Server, targetServer: Server = None):
        """
        Signal to MC intent to delete a server
        :param server: signal for deletion
        :param targetServer: optional new server for current players to transition over towards
        :return: True if the signal was applied
        """
        # pool = self.batchclient.check_or_create_pool(self.batchclient.pool_id)
        if self.check_is_pool_steady() and not self.flag_transition:
            if server.state == Server.State.STABLE:
                if server.playercount > 0 and (targetServer is None or targetServer.state != Server.State.STABLE):
                    return False # Desired server has players! needs a target server that is stable.

                server.state = Server.State.REQUESTED_DEACTIVATION
                server.decommission(targetServer)
                if targetServer is not None:
                    targetServer.state = Server.State.WAITING_FOR_MERGE
                self.flag_transition = True
                return True
        return False

    def add_logical_server(self, server: Server):
        if server not in self.servers:
            self.servers.append(server)
            self.servercount += 1
            return True
        return False

    def getServerForTeam(self, team):
        """
        THis gets the server that a player can be added to
        :param team: the team whose server we need
        :return: {Server} object that can add a player.
        """
        if team not in self.teams_to_servers:
            self.teams_to_servers.update({team: self.__get_next_available_server()})

        return self.teams_to_servers[team]

    def __get_next_available_server(self):
        """
        :return: server with least number of players on it (for a new team to spawn) that is running
        """
        self.servers.sort()
        for srv in self.servers:
            if srv.eligible_for_new_teams():
                return srv



