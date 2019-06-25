#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2017 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import cockpit.util.Mrc as Mrc

class TruncatedMrcFiles(unittest.TestCase):
    def test_adjust_data_shape(self):
        ## An array of test cases, each a 3 element tuple specifying
        ## array_size, expected_shape, and adjusted_shape (the return
        ## value)
        test_cases = [
            (100, (10, 10), (10, 10)),
            (20, (10, 10), (2, 10)),
            (15, (10, 10), (2, 10)),
            (621, (3, 23, 27), (1, 23, 27)),
            (26, (3, 23, 27), (1, 1, 26)),
            (27, (3, 23, 27), (1, 1, 27)),
            (28, (3, 23, 27), (1, 2, 27)),
            (13893632, (2, 135, 2, 512, 512), (1, 27, 2, 512, 512)),
            (26, (27,), (26,)),
            (27, (27,), (27,)),
            (0, (10, 10), (0, 0)),
        ]
        for case in test_cases:
            numel = case[0]
            shape = case[1]
            expected_shape = case[2]
            self.assertEqual(Mrc.adjusted_data_shape(numel, shape),
                             expected_shape)

        test_cases = [
            (150, (10, 10)),
        ]
        for case in test_cases:
            with self.assertRaisesRegex(ValueError, 'data too large'):
                numel = case[0]
                shape = case[1]
                Mrc.adjusted_data_shape(numel, shape)
