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

import cockpit.handlers.stagePositioner

class testStagePositioner(unittest.TestCase):

    def setUp(self):
        self.callbacks = unittest.mock.MagicMock()
        self.args = {
            'name': 'mock',
            'groupName': 'testsuite',
            'isEligibleForExperiments': True,
            'callbacks': self.callbacks,
            'axis': 0,
            'hardLimits': (-10, 10),
        }

    def test_default_soft_limits(self):
        PH = cockpit.handlers.stagePositioner.PositionerHandler(**self.args)
        self.assertEqual(PH.getSoftLimits(), list(self.args['hardLimits']))

    def test_soft_limits_present(self):
        self.args['softLimits'] = (-5, 5)
        PH = cockpit.handlers.stagePositioner.PositionerHandler(**self.args)
        ## XXX: Even if the soft limits in the constructor were a
        ## tuple, internally is changed to a list.  Makes sense
        ## internally, but maybe the return should be a tuple.
        self.assertEqual(PH.getSoftLimits(), [-5, 5])


if __name__ == '__main__':
    unittest.main()
