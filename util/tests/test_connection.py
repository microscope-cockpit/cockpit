import unittest
import mock
import util.connection as connection

from mockManagers import replace_with_mock

def doNothing():
    pass

class TestConnection(unittest.TestCase):

    def setUp(self):
        connection.depot = mock.Mock()
        self.servermock = mock.Mock(name='serverMock')
        connection.depot.getHandlersOfType.return_value = [self.servermock]

        self.name = 'Service'
        self.ip = '0.0.0.0'
        self.port = 0
        self.connectstring = 'PYRO:{}@{}:{}'.format(self.name, self.ip, self.port)
        self.link = connection.Connection(self.name, self.ip, self.port, self.ip)

    def test___init__(self):
        '''Test no errors thrown in connection init.
        '''
        connection.Connection('None', '0.0.0.0', 0, '0.0.0.0')


    def test_connect(self):

        with replace_with_mock(connection, 'Pyro4') as pyroMock:
            self.link.connect(doNothing)
            pyroMock.Proxy.assert_called(self.connectstring)
        self.servermock.register.assert_called(doNothing, self.ip)


    def test_connect_no_callback(self):
        '''Test error is thrown if no callback is given.
        TODO: Is this an somthing that needs to be tested for?'''
        pass


    def test_disconnect(self):
        with replace_with_mock(connection, 'Pyro4') as pyroMock:
            self.link.connect(doNothing)
            self.link.disconnect()
        self.servermock.unregister.assert_called(doNothing)


    def test_disconnect_no_callback(self):
        with replace_with_mock(connection, 'Pyro4') as pyroMock:
            self.link.disconnect()
        self.assertEqual(self.servermock.unregister.call_count, 0)

    def test_getIsConnected(self):
        with replace_with_mock(connection, 'Pyro4') as pyroMock:
            self.link.connect(doNothing)
        self.assertTrue(self.link.getIsConnected())

if __name__ == '__main__':
    unittest.main()
