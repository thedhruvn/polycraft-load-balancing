import configparser

from modules.BatchPool import BatchPool
from modules.Server import Server


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

    def initializeManager(self, pool_id = None):
        self.batchclient = BatchPool(config=self.raw_config_file)
        if pool_id is None:
            pool_id = self.config.get('POOL', 'id')
        self.batchclient.check_or_create_pool(pool_id)
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
            self.addServer(newSrv)


    def addServer(self, server: Server):
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



