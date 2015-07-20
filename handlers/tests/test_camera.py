import handlers.camera

import unittest
import mock


class testCamera(unittest.TestCase):

    def setUp(self):
        self.callbackMock = mock.MagicMock()
        self.args = {'name':'camera', 'groupName':'group',
                     'callbacks':self.callbackMock,
                     'exposureMode':handlers.camera.TRIGGER_BEFORE}


    def testOnDrawerChangeSetsColor(self):
        drawerHandler = mock.Mock()
        drawerHandler.getColorForCamera.return_value = 'Color'
        drawerHandler.getDyeForCamera.return_value = None
        drawerHandler.getWavelengthForCamera.return_value = 555

        camera = handlers.camera.CameraHandler(**self.args)
        camera.onDrawerChange(drawerHandler)
        self.assertEqual(camera.color, 'Color')


    def testOnDrawerChangeSetsColor(self):
        drawerHandler = mock.Mock()
        drawerHandler.getColorForCamera.return_value = None
        drawerHandler.getDyeForCamera.return_value = 'Dye'
        drawerHandler.getWavelengthForCamera.return_value = 555

        camera = handlers.camera.CameraHandler(**self.args)
        camera.onDrawerChange(drawerHandler)
        self.assertEqual(camera.descriptiveName,
                         'Dye ({})'.format(self.args['name']))


    def testOnDrawerChangeSetsWavelength(self):
        drawerHandler = mock.Mock()
        drawerHandler.getColorForCamera.return_value = 'Color'
        drawerHandler.getDyeForCamera.return_value = None
        drawerHandler.getWavelengthForCamera.return_value = 555

        camera = handlers.camera.CameraHandler(**self.args)
        camera.onDrawerChange(drawerHandler)
        self.assertEqual(camera.wavelength, 555)


    @mock.patch('handlers.camera.events')
    def testSetEnabledSendsCallback(self, mockEvents):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(True)

        self.callbackMock['setEnabled'].assert_called_with('camera', True)


    @mock.patch('handlers.camera.events')
    def testSetEnabledSendsCorrectEvent(self, mockEvents):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(True)

        mockEvents.subscribe.assert_called_with('prepare for experiment',
                                                camera.prepareForExperiment)


    @mock.patch('handlers.camera.events')
    def testSetEnabledSendsCorrectEvent(self, mockEvents):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(True)
        mockEvents.subscribe.assert_called_with('prepare for experiment',
                                                camera.prepareForExperiment)

    @mock.patch('handlers.camera.events')
    def testSetEnabledSendsCorrectEvent_disable(self, mockEvents):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(False)
        mockEvents.unsubscribe.assert_called_with('prepare for experiment',
                                                  camera.prepareForExperiment)


    def testEnabledGetter(self):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(True)
        self.assertTrue(camera.getIsEnabled)


    def testGetTimeBetweenExposures(self):
        self.callbackMock['getTimeBetweenExposures'].return_value = 50
        camera = handlers.camera.CameraHandler(**self.args)

        self.assertEqual(camera.getTimeBetweenExposures(), 50)
        self.callbackMock['getTimeBetweenExposures'].assert_called_with('camera',
                                                                        False)


    def testGetMinExposureTime(self):
        self.callbackMock['getMinExposureTime'].return_value = 50
        self.callbackMock.__contains__ = lambda _, __: True
        camera = handlers.camera.CameraHandler(**self.args)

        self.assertEqual(camera.getMinExposureTime(), 50)
        self.callbackMock['getMinExposureTime'].assert_called_with('camera')


    def testSetExposureTime(self):
        camera = handlers.camera.CameraHandler(**self.args)
        camera.setExposureTime(50)
        self.callbackMock['setExposureTime'].assert_called_with('camera', 50)
