import mock
import unittest

import handlers.lightPower


class testLightPowerHandler(unittest.TestCase):

    def setUp(self):
        self.callbacks = mock.MagicMock()
        self.args = {'name':'name', 'groupName':'grpname', 'callbacks':self.callbacks,
                     'wavelength':555, 'minPower':50, 'maxPower':50,
                     'color':'green'}


    @mock.patch('handlers.lightPower.util')
    def test_onLogin(self, mockutil):
        mockutil.userConfig.getValue.return_value = 1
        LPHandler = handlers.lightPower.LightPowerHandler(**self.args)
        LPHandler.onLogin('username')

        mockutil.userConfig.getValue.assert_called_with('username-lightpower', default = 0.01)
        self.callbacks['setPower'].assert_called_with('name', 1)
