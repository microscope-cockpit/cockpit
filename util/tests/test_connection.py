import unittest
import connection
class TestConnection(unittest.TestCase):
    def test___init__(self):
        '''Test no errors thrown in connection init.
        '''
        connection.Connection('None', 0.0.0.0, 0, 0.0.0.0)


    def test_connect(self):
        # connection = Connection(serviceName, ipAddress, port, localIp)
        # self.assertEqual(expected, connection.connect(callback, timeout))
        assert False # TODO: implement your test here

    def test_disconnect(self):
        # connection = Connection(serviceName, ipAddress, port, localIp)
        # self.assertEqual(expected, connection.disconnect())
        assert False # TODO: implement your test here

    def test_getIsConnected(self):
        # connection = Connection(serviceName, ipAddress, port, localIp)
        # self.assertEqual(expected, connection.getIsConnected())
        assert False # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()
