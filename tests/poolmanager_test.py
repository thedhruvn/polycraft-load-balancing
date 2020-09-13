import unittest
from modules import BatchPool, PoolManager
from modules.Server import Server


class MyTestCase(unittest.TestCase):
    def test_pool_exists(self):

        batch = BatchPool.BatchPool()
        batch.check_or_create_pool("test4")

        self.assertEqual(batch.client.pool.exists("test4"), True)

    #
    def test_print_mc_ports(self):

        servers = []

        batch = BatchPool.BatchPool()
        id = "test4"
        batch.check_or_create_pool(id)
        for node in batch.client.compute_node.list(id):
            ip = None
            minecraftPort = None
            APIPort = None

            for endpoint in node.endpoint_configuration.inbound_endpoints:
                if 'minecraft' in endpoint.name:
                    minecraftPort = endpoint.frontend_port
                    ip = endpoint.public_ip_address
                    print(f"minecraft: {ip}:{minecraftPort}")
                if 'api' in endpoint.name:
                    APIPort = endpoint.frontend_port
                    ip = endpoint.public_ip_address
                    print(f"api: {ip}:{APIPort}")

            servers.append(Server(ip=ip, port=minecraftPort, api_port=APIPort))

        self.assertEqual(len(servers), 2)

    def test_pool_manager_init(self):
        pm = PoolManager.PoolManager()
        pm.initializeManager()
        self.assertEqual(pm.servercount, 2)

    def test_add_jobs(self):
        batch = BatchPool.BatchPool()
        batch.check_or_create_pool("test4")
        batch.launch_mc_server(2)

if __name__ == '__main__':
    unittest.main()
