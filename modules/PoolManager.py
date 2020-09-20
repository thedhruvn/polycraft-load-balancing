import configparser

from azure.batch.models import BatchErrorException
from azure.batch.models import ComputeNodeState

from modules.BatchPool import BatchPool
from modules.Server import Server
from root import *
from enum import Enum


class PoolManager:

    def __init__(self, config=os.path.join(ROOT_DIR, 'configs/azurebatch.cfg')):
        self.config = configparser.ConfigParser()
        self.config.read(config)
        # self.creds_raw_file = credentials
        self.raw_config_file = config

        # self.state = PoolManager.State(0, {})
        self.servercount = 0
        self.teams_to_servers = {}
        self.servers = []
        self.player_to_team_lookup = {}
        self.player_to_server_lookup = {}

        self.flag_transition = False  # Set to true during expansions OR contractions to prevent multiple triggers
        self.batchclient: BatchPool = BatchPool(config=self.raw_config_file)
        self.state = PoolManager.State.STARTING

    class State(Enum):
        STARTING = -1       # True when the constructor is called and it has not yet reached allocation_state = steady
        STABLE = 0          # This is true when the pool.allocation_state == steady (i.e., the pool can be altered)
        FLAG_TO_SHIFT = 1   # True when the Load Balancer requests a change but the pool is still steady.
        TRANSITIONING = 2   # This is true when the pool.allocation_state != steady (i.e., the pool is changing somehow)
        CLOSING = 3         # Unnecessary?

    def check_is_pool_steady(self):
        """
        THis method is unchecked! Please call poll_servers_and_update to get the updated state before calling this.

        :return: True if the pool's allocation state is steady. False otherwise.
        """
        return self.state == PoolManager.State.STABLE

    def poll_servers_and_update(self):
        """
        Updates the pool State (based on its allocation_state variable)
        Queries all servers and updates their Server State.

        NOTE: this is expensive to run and should be running during the config's specified interval to prevent delays
        """

        if self.batchclient:
            pool_id = self.batchclient.pool_id
            try:
                pool = self.batchclient.client.pool.get(pool_id)
                if pool is not None and 'steady' in pool.allocation_state.value:
                    # Case: Pool is stable but the load balancer is intending to change that soon
                    if self.state != PoolManager.State.FLAG_TO_SHIFT:
                        # Only set to stable if the Pool doesn't have a plan to shift
                        self.state = PoolManager.State.STABLE

                # Case: Pool is still in startup
                elif self.state == PoolManager.State.STARTING:
                    return    # Don't run server.poll until the pool is up.
                    # pass    # Pool is still starting - don't change its state and don't poll servers

                # Case: Pool is not steady
                else:
                    self.state = PoolManager.State.TRANSITIONING
            except BatchErrorException as e:
                self.state = PoolManager.State.TRANSITIONING
            except Exception as e:
                print(e)
                self.state = PoolManager.State.TRANSITIONING

            self.teams_to_servers.clear()
            for server in self.servers:
                server.poll()
                self.teams_to_servers.update({team: server for team in server.teams})
        else:
            self.state = PoolManager.State.STARTING  # If the batchclient is null, the pool must be starting or closing.

    def update_server_list(self):
        """
        Polls all servers in a given pool and updates the PoolManager's list of servers
        :return: False if the pool is undefined or if the pool is not at Steady State.
        """
        # if pool_id is None:
        if self.batchclient:
            pool_id = self.batchclient.pool_id
        else:
            return False

        if self.check_is_pool_steady():
            self.servers.clear()
            self.servercount = 0
            for node in self.batchclient.client.compute_node.list(pool_id):     #noTODO: Skip based on Node ComputeState?
                if node.state in [ComputeNodeState.leaving_pool, ComputeNodeState.offline, ComputeNodeState.unusable]:
                    continue  # Skip compute nodes that are leaving, shutdown, or otherwise useless.
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

                newSrv = Server(node_id=node.id, ip=ip, port=minecraftPort, api_port=APIPort)
                newSrv.poll()  # Update its state
                self.add_logical_server(newSrv)
            return True
        return False

    def initializeManager(self, pool_id=None):
        """
        Connects Pool Manager to Azure batch on pool_id
        :param pool_id: the ID of the pool to connect to. If None, uses the default from the Config file
        :return: True if a new Pool is created; False if attaching to an existing pool
        """
        # self.batchclient = BatchPool(config=self.raw_config_file)
        if pool_id is None:
            pool_id = self.config.get('POOL', 'id')
        existing_pool = self.batchclient.check_or_create_pool(pool_id)
        if existing_pool is None:
            return True  # This should be the case for a newly created pool

        return False

    def expand_pool_add_server(self, count):
        """
        Attempt to expand the batch pool by a countable number of nodes
        Checks to see if the pool's allocation state is Steady before attempting to expand
        :param count: number of nodes to add (must be positive)
        :return: True if the pool's resize was successfully submitted to Azure
        """
        if count > 0 and self.batchclient is not None:
            new_srv_count = count
            pool = self.batchclient.check_or_create_pool(self.batchclient.pool_id)
            count += len(self.servers)
            if pool is not None and 'steady' in pool.allocation_state.value:  # and not self.flag_transition:
                if self.batchclient.expand_pool(count):     # This triggers the pool.allocation_state to change!
                    # self.flag_transition = True
                    for i in range(0, new_srv_count):
                        self.batchclient.add_task_to_start_server()  # Add task to the ongoing server.
                    self.poll_servers_and_update()
                    return True

        # TODO:
        return False

    def actual_remove_server(self, server: Server):
        """
        Tell the pool to dequeue a Node
        :param server: The server to remove
        :return: True if msg passed successfully to the server. False otherwise.
        """
        if self.state in [PoolManager.State.STABLE, PoolManager.State.FLAG_TO_SHIFT]:  # Run if stable (due to crash) or if the pool is flagged to shrink
            if server.state == Server.State.DEACTIVATED or server.state == Server.State.CRASHED:
                if self.batchclient.remove_node_from_pool(server.node_id):   #  CONFIRMED this triggers allocation_state change!

                    #  print(f"Pool State: {self.batchclient.client.pool.get(self.batchclient.pool_id).allocation_state.value}")
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
        if self.check_is_pool_steady():     # and not self.flag_transition:
            if server.state == Server.State.STABLE:
                if server.playercount > 0 and (targetServer is None or targetServer.state != Server.State.STABLE):
                    return False  # Desired server has players! needs a target server that is stable.

                if targetServer is not None:
                    server.decommission(targetServer)
                    targetServer.state = Server.State.WAITING_FOR_MERGE
                else:
                    server.decommission()

                self.state = PoolManager.State.FLAG_TO_SHIFT   # Alert the Load Balancer that a msg to shift is received
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

    def __get_next_available_server(self) -> Server:
        """
        :return: server with least number of players on it (for a new team to spawn) that is running
        """
        self.servers.sort()
        for srv in self.servers:
            if srv.eligible_for_new_teams():
                return srv
        raise   # Throw an error if no servers are available - this should NEVER happen.
