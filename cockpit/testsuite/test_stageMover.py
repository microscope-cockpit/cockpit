#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

from cockpit.interfaces import stageMover


class TestStepSizeSense(unittest.TestCase):
    def assertNextStepSize(self, step: float, expected: float) -> None:
        self.assertEqual(stageMover.SensibleNextStepSize(step), expected,
                         'expected step size after %f to be %f'
                         % (step, expected))

    def assertPreviousStepSize(self, step: float, expected: float) -> None:
        self.assertEqual(stageMover.SensiblePreviousStepSize(step), expected,
                         'expected step size before %f to be %f'
                         % (step, expected))


    def test(self):
        for step, up, down in [(0.00001, 0.00002, 0.000005),
                               (0.00004, 0.00005, 0.00002),
                               (0.00009, 0.0001, 0.00005),
                               (0.9, 1, 0.5),
                               (0.5, 1, 0.2),
                               (0.3, 0.5, 0.2),
                               (0.2, 0.5, 0.1),
                               (0.1, 0.2, 0.05),
                               (1, 2, 0.5),
                               (2, 5, 1),
                               (3, 5, 2),
                               (5, 10, 2),
                               (9, 10, 5),
                               (10, 20, 5),
                               (15, 20, 10),
                               (20, 50, 10),
                               (30, 50, 20),
                               (50, 100, 20),
                               (60, 100, 50),
                               (99, 100, 50),
                               (100, 200, 50),
                               (130, 200, 100),
                               (150, 200, 100),
                               (2000.1, 5000, 2000),]:
            self.assertNextStepSize(step, up)
            self.assertPreviousStepSize(step, down)


if __name__ == '__main__':
    unittest.main()
