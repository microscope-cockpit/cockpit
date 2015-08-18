import unittest
import mock

import devices.dsp
DSPDevice = devices.dsp.DSPDevice

class TestDSP(unittest.TestCase):

    def setUp(self):

        self.mockLight = mock.MagicMock()
        self.mockLight.name = 'l'

        self.mockCamera = mock.MagicMock()
        self.mockCamera.name = 'c'

        devices.dsp.config = mock.MagicMock()
        devices.dsp.config.has_section.return_value = True
        devices.dsp.LIGHTS = { 'l': {'triggerLine':1} }
        devices.dsp.CAMERAS = { 'c': {'triggerLine':2} }
        # analog line setup is done in getHandlers

        self.dsp = DSPDevice()

        self.dsp.connection = mock.MagicMock()

        with mock.patch('devices.dsp.depot') as mdepot:
            mdepot.getHandlerWithName = lambda x: x
            self.dsp.finalizeInitialization()


    def test_generateProfile_numDigitalLines(self):
        events = [ (0, 'l', 1)]
        dscr, digitals, analogs = DSPDevice.generateProfile(self.dsp, events, 0)
        self.assertEqual(len(digitals), 2) # 2 digital lines are defined

    def test_generateProfile_digitalTime(self):
        events = [ (0, 'l', 1),
                   (1, 'l', 0),
                   (2, 'l', 1) ]
        dscr, digitals, analogs = DSPDevice.generateProfile(self.dsp, events, 0)
        self.assertEqual(len(digitals), 3) # 2 timepoints, on and off
        self.assertEqual(digitals[0][1], 1) # turn on at t=0
