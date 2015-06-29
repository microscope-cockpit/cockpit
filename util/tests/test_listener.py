import unittest
import mock
import Pyro4

import util.listener

def doNothing():
    pass

class testListener(unittest.TestCase):

    def setUp(self):
        #self.pyroProxy = mock.create_autospec(Pyro4.Proxy)
        self.pyroProxy = mock.Mock(name='pyro proxy')
        util.listener.depot = mock.MagicMock()
        self.server = mock.Mock(name='mock server')
        util.listener.depot.getHandlersOfType.return_value = [self.server]

    def test_creation(self):
        listener = util.listener.Listener(self.pyroProxy,
                                          callback=doNothing)


    def test_connect(self):
        '''Tests that the listener calls the correct server functions.'''
        self.server.register.return_value = 'uri'
        listener = util.listener.Listener(self.pyroProxy, localIp='0.0.0.0',
                                          callback=doNothing)
        listener.connect()

        self.server.register.assert_called(None, '0.0.0.0')
        self.pyroProxy.recieveClient.assert_called('uri')
        self.assertTrue(listener._listening)


    def test_connect_callback_in_connect(self):
        '''Test that the callback can be provided in either location.'''
        self.server.register.return_value = 'uri'
        listener = util.listener.Listener(self.pyroProxy, localIp='0.0.0.0')
        listener.connect(callback=doNothing)

        self.server.register.assert_called(None, '0.0.0.0')
        self.pyroProxy.recieveClient.assert_called('uri')


    def test_connect_no_callback(self):
        '''Test that an exception is raised if no callback is provided.'''
        listener = util.listener.Listener(self.pyroProxy, localIp='0.0.0.0')
        with self.assertRaises(Exception):
            listener.connect()


    def test_disconnect(self):
        '''Test that disconnect unregisters the callback.'''
        listener = util.listener.Listener(self.pyroProxy, localIp='0.0.0.0',
                                          callback=doNothing)
        listener.connect()
        listener.disconnect()

        self.server.unregister.assert_called(doNothing)
        self.assertFalse(listener._listening)


    def test_only_one_callback_may_exist(self):
        '''self._listening only permits one callback to be registed at once.'''
        listener = util.listener.Listener(self.pyroProxy, localIp='0.0.0.0')
        listener.connect(callback=doNothing)
        listener.connect(callback=doNothing)

        self.server.unregister.assert_called(doNothing)
