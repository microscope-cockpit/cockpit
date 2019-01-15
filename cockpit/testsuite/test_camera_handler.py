#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
## Copyright (C) 2019 Thomas Park <thomasparks@outlook.com>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import unittest.mock

import cockpit.depot
import cockpit.events
import cockpit.interfaces.imager
import cockpit.handlers.camera


class CameraHandlerTestCase(unittest.TestCase):
    def setUp(self):
        ## On each test we will be creating new handlers which may
        ## conflict with handlers created in previous tests.  So just
        ## build a new depot and reinitialise the imager.
        cockpit.depot.deviceDepot = cockpit.depot.DeviceDepot()
        cockpit.interfaces.imager.initialize()

        self.callback_mocks = {
            'setEnabled' : unittest.mock.Mock(side_effect=lambda n, s : s),
        }

        self.args = {
            'name': 'mock',
            'groupName': 'testsuite',
            'callbacks': self.callback_mocks,
            'exposureMode': cockpit.handlers.camera.TRIGGER_BEFORE,
        }

    def test_update_filter(self):
        event_handler = unittest.mock.Mock()
        cockpit.events.subscribe('filter change', event_handler)

        try:
            camera = cockpit.handlers.camera.CameraHandler(**self.args)
            camera.updateFilter('test-dye', 512.0)
        finally:
            cockpit.events.unsubscribe('filter change', event_handler)

        event_handler.assert_called_once()
        self.assertEqual(camera.dye, 'test-dye')
        self.assertEqual(camera.wavelength, 512.0)

    def test_descriptive_name(self):
        camera = cockpit.handlers.camera.CameraHandler(**self.args)
        camera.updateFilter('Test-Dye', 512.0)
        self.assertEqual(camera.descriptiveName,
                         self.args['name'] + ' (Test-Dye)')


    def test_camera_enable_event(self):
        camera = cockpit.handlers.camera.CameraHandler(**self.args)

        event_handler = unittest.mock.Mock()
        cockpit.events.subscribe('camera enable', event_handler)
        try:
            camera.setEnabled(True)
        finally:
            cockpit.events.unsubscribe('camera enable', event_handler)

        event_handler.assert_called_once()
        event_handler.assert_called_with(camera, True)
        self.callback_mocks['setEnabled'].assert_called_with('mock', True)


    @unittest.mock.patch('cockpit.handlers.camera.events')
    def test_set_enabled_sends_experiment_event(self, mockEvents):
        camera = cockpit.handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(True)

        mockEvents.subscribe.assert_called_with('prepare for experiment',
                                                camera.prepareForExperiment)

    @unittest.mock.patch('cockpit.handlers.camera.events')
    def testSetEnabledSendsCorrectEvent_disable(self, mockEvents):
        camera = cockpit.handlers.camera.CameraHandler(**self.args)
        camera.setEnabled(False)
        mockEvents.unsubscribe.assert_called_with('prepare for experiment',
                                                  camera.prepareForExperiment)

    def test_enabled_getter(self):
        camera = cockpit.handlers.camera.CameraHandler(**self.args)
        self.assertFalse(camera.getIsEnabled())
        camera.setEnabled(True)
        self.assertTrue(camera.getIsEnabled())
        camera.setEnabled(False)
        self.assertFalse(camera.getIsEnabled())

    def test_get_time_between_exposures(self):
        callback = unittest.mock.Mock(return_value=50)
        self.args['callbacks'] = {'getTimeBetweenExposures' : callback}
        camera = cockpit.handlers.camera.CameraHandler(**self.args)

        self.assertEqual(camera.getTimeBetweenExposures(), 50)
        callback.assert_called_with('mock', False)

    def testGetMinExposureTime(self):
        callback = unittest.mock.Mock(return_value=50)
        self.args['callbacks'] = {'getMinExposureTime' : callback}
        camera = cockpit.handlers.camera.CameraHandler(**self.args)

        self.assertEqual(camera.getMinExposureTime(), 50)
        callback.assert_called_with('mock')

    def testSetExposureTime(self):
        callback = unittest.mock.Mock()
        self.args['callbacks'] = {'setExposureTime' : callback}
        camera = cockpit.handlers.camera.CameraHandler(**self.args)

        camera.setExposureTime(50)
        callback.assert_called_with('mock', 50)


if __name__ == '__main__':
    unittest.main()
