import unittest
from modules import BatchPool, PoolManager
from modules.Server import Server
import time

class MyTestCase(unittest.TestCase):

    POOL_ID = "test9"

    def test_pool_exists(self):

        batch = BatchPool.BatchPool()
        batch.check_or_create_pool(MyTestCase.POOL_ID)

        self.assertEqual(batch.client.pool.exists(MyTestCase.POOL_ID), True)

    #
    def test_print_mc_ports(self):

        servers = []

        batch = BatchPool.BatchPool()
        id = MyTestCase.POOL_ID
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
        success = pm.initializeManager(MyTestCase.POOL_ID)
        self.assertEqual(success, True)
        if success:
            self.assertEqual(pm.servercount, 2)

    def test_load_balancer_main_init(self):
        max_retry_initialize = 10
        pool = PoolManager.PoolManager()
        id = 'test06'
        pool.initializeManager(id)
        counter = 0
        initialized = pool.check_is_pool_steady(id)
        while not initialized and counter < max_retry_initialize:
            print("waiting for initialization...")
            time.sleep(90)
            counter += 1
            initialized = pool.check_is_pool_steady(id)

        should_continue = counter < max_retry_initialize

        if should_continue:
            initialized = pool.update_server_list(id)
            # self._launch_lobby_thread()

        self.assertEqual(pool.servercount, 2)

    def test_add_jobs(self):
        batch = BatchPool.BatchPool()
        batch.check_or_create_pool(MyTestCase.POOL_ID)
        batch.start_mc_server_job_pool(2)

if __name__ == '__main__':
    unittest.main()
