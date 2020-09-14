import unittest

from modules import PoolManager
from main.LoadBalancerMain import LoadBalancerMain
import time

class MyTestCase(unittest.TestCase):

    def test_LB_main(self):
        lb = LoadBalancerMain()
        lb.main()
        self.assertEqual(True, False)

    def test_add_nodes(self):

        max_retry_initialize = 10
        pool = PoolManager.PoolManager()
        id = 'test06'
        pool.initializeManager(id)
        counter = 0
        initialized = pool.check_is_pool_steady(id)
        while not initialized and counter < max_retry_initialize:
            print("waiting for initialization...")
            time.sleep(60)
            counter += 1
            initialized = pool.check_is_pool_steady(id)

        should_continue = counter < max_retry_initialize

        if should_continue:
            initialized = pool.update_server_list(id)
            # self._launch_lobby_thread()

        # self.assertEqual(pool.servercount, 2)

        if pool.expand_pool_add_server(2):
            time.sleep(10)
            initialized = pool.check_is_pool_steady(id)
            while not initialized and counter < max_retry_initialize:
                print("waiting for expansion...")
                time.sleep(60)
                counter += 1
                initialized = pool.check_is_pool_steady(id)

            should_continue = counter < max_retry_initialize

            if should_continue:
                pool.batchclient.launch_mc_server(2)
                time.sleep(5)
                initialized = pool.update_server_list(id)
                # self._launch_lobby_thread()

            self.assertEqual(pool.servercount, 3)



if __name__ == '__main__':
    unittest.main()
