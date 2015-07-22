import unittest
import mock

import handlers.lightSource

class TestLightSourceHandler(unittest.TestCase):

    def setUp(self):
        self.args = {'name':'light', 'groupName':'GrpName', 'callbacks':[],
                     'wavelength':555, 'exposureTime':5}


    @mock.patch('handlers.lightSource.events')
    def test_init(self, mockevents):
        light = handlers.lightSource.LightHandler(**self.args)
        mockevents.subscribe.assert_any_call('save exposure settings', light.onSaveSettings)
        mockevents.subscribe.assert_any_call('load exposure settings', light.onLoadSettings)

    def test_onSaveSettings(self):
        light = handlers.lightSource.LightHandler(**self.args)
        light.getIsEnabled = lambda: True
        light.getExposureTime = lambda: 5
        settings = {}
        light.onSaveSettings(settings)
        self.assertEqual(settings['light']['isEnabled'], True)
        self.assertEqual(settings['light']['exposureTime'], 5)


    def test_onLoadSettings(self):
        light = handlers.lightSource.LightHandler(**self.args)
        light.setExposureTime = mock.Mock()
        light.setEnabled = mock.Mock()
        settings = {'light':{'isEnabled':True, 'exposureTime':10}}
        light.onLoadSettings(settings)
        light.setExposureTime.assert_called_with(10)
        light.setEnabled.assert_called_with(True)


    @mock.patch('handlers.lightSource.events')
    def test_toggle(self, mockevents):
        self.args['callbacks'] = mock.MagicMock()
        light = handlers.lightSource.LightHandler(**self.args)
        light.getIsExposingContinuously = lambda: False
        light.toggle(False)
        mockevents.publish.assert_Called_with('light source enable', light, False)


    @mock.patch('handlers.lightSource.events')
    def test_toggle(self, mockevents):
        self.args['callbacks'] = mock.MagicMock()
        light = handlers.lightSource.LightHandler(**self.args)
        light.getIsExposingContinuously = lambda: False
        light.toggle(False)
        mockevents.publish.assert_Called_with('light source enable', light, False)


    @mock.patch('handlers.lightSource.wx')
    @mock.patch('handlers.lightSource.events')
    def test_toggle_ContExpose(self, mockevents, mockwx):
        '''When it's on cont expose mode, it uses the GUI logic to
        reactivate the light. Tested seperatly.
        '''
        self.args['callbacks'] = mock.MagicMock()
        light = handlers.lightSource.LightHandler(**self.args)
        light.getIsExposingContinuously = lambda: True
        light.toggle(False)
        self.args['callbacks']['setExposing'].assert_called_with('light', False)


    def test_setEnabled(self):
        light = handlers.lightSource.LightHandler(**self.args)
        light.getIsExposingContinuously = lambda: False
        light.activeButton = mock.Mock()
