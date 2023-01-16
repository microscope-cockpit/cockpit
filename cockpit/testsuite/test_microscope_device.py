#!/usr/bin/env python3

## Copyright (C) 2023 David Miguel Susano Pinto <carandraug@gmail.com>
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

from microscope.simulators import SimulatedFilterWheel

import cockpit.depot
from cockpit.devices.dummies import _MicroscopeTestDevice
from cockpit.devices.microscopeDevice import MicroscopeBase


class MicroscopeDeviceWithTestSetting(SimulatedFilterWheel):
    # The Microscope device behind the Cockpit device for these tests.
    # We don't actually care what device type it is, we just use
    # filterwheels because they're the simplest.
    def __init__(self):
        super().__init__(positions=6)
        self._test_setting = False  # default value
        self.add_setting(
            "cockpit-test-setting",
            "bool",
            self.get_test_setting,
            self.set_test_setting,
            None,
        )

    def get_test_setting(self):
        return self._test_setting

    def set_test_setting(self, new_value):
        self._test_setting = new_value


class CockpitDeviceWithTestSetting(_MicroscopeTestDevice, MicroscopeBase):
    # The Cockpit device which the rest of Cockpit handles and that
    # proxies the Microscope device.  Because we don't actually case
    # what device type it is, we just use MicroscopeBase.
    def __init__(self, *args, **kwargs):
        super().__init__(MicroscopeDeviceWithTestSetting(), *args, **kwargs)

    # At the end of `MicroscopeBase.finalizeInitialization` (which is
    # where the settings section from the depot file are applied), the
    # user config is read and written back.  We don't want to do that
    # during the test so do nothing here.
    def _readUserConfig(self):
        pass


class TestMicroscopeSettings(unittest.TestCase):
    setting_name = "cockpit-test-setting"

    def assertSettingIsDefault(self, dev):
        self.assertFalse(dev._proxy.get_setting(self.setting_name))

    def assertSettingChanged(self, dev):
        self.assertTrue(dev._proxy.get_setting(self.setting_name))

    # During each each test, new handlers are created which are added
    # to depot (a global singleton).  To avoid issues, we create a new
    # DeviceDepot instance before each test and remove it at the end.
    def setUp(self):
        cockpit.depot.deviceDepot = cockpit.depot.DeviceDepot()

    def tearDown(self):
        cockpit.depot.deviceDepot = None

    # Settings are parsed and applied during `finalizeInitialization`
    # so we need to have DeviceDepot does the whole init routine first.
    def _do_the_whole_init_routine(self, device_name, config_dict):
        device = CockpitDeviceWithTestSetting(device_name, config_dict)
        cockpit.depot.deviceDepot.initDevice(device)
        device.finalizeInitialization()
        return device

    def test_default_setting(self):
        # We will test if we can parse and apply a setting value to
        # the device which means we need to modify the setting default
        # value.  This tests that the default value really is what we
        # think we are (`False`) so on the other tests we can
        # confidently test setting it to something else (`True`).
        dev = self._do_the_whole_init_routine("test device", {})
        self.assertSettingIsDefault(dev)

    def test_setting_in_config(self):
        dev = self._do_the_whole_init_routine(
            "test device", {"settings": "%s: True" % self.setting_name}
        )
        self.assertSettingChanged(dev)

    def test_setting_in_config_with_equals(self):
        dev = self._do_the_whole_init_routine(
            "test device", {"settings": "%s= True" % self.setting_name}
        )
        self.assertSettingChanged(dev)

    def test_parsing_with_whitespace(self):
        # Regression test for issue #840 (uses non-greedy modifiers to
        # capture setting name to ignore whitespace)
        dev_colon = self._do_the_whole_init_routine(
            "test device #1 for #840",
            {"settings": "%s : True" % self.setting_name},
        )
        self.assertSettingChanged(dev_colon)
        dev_equals = self._do_the_whole_init_routine(
            "test device #2 for #840",
            {"settings": "%s = True" % self.setting_name},
        )
        self.assertSettingChanged(dev_equals)


if __name__ == "__main__":
    unittest.main()
