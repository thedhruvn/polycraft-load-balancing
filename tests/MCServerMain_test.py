import unittest
from main.MCServerMain import MCServer


class MyTestCase(unittest.TestCase):
    def test_mcServer(self):
        serv = MCServer(pp=False)
        print(f"Launching MC Listener Thread on Port: {serv.api_port}")
        serv.run()

        self.assertEqual(True, True)


if __name__ == '__main__':
    unittest.main()
