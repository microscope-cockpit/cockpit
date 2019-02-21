#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import cockpit.depot

class TestTypeFromClassName(unittest.TestCase):
    def _assertTypes(self, class_name, expected_type):
        observed_type = cockpit.depot._class_name_to_type(class_name)
        self.assertEqual(observed_type, expected_type)

    def test_builtin_type(self):
        self._assertTypes('str', str)

    def test_python_stdlib_type(self):
        import decimal
        self._assertTypes('decimal.Decimal', decimal.Decimal)

    def test_cockpit_device_type(self):
        import cockpit.devices.dummyLights
        self._assertTypes('cockpit.devices.dummyLights.DummyLights',
                          cockpit.devices.dummyLights.DummyLights)


if __name__ == '__main__':
    unittest.main()
