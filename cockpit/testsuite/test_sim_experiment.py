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

import numpy

import cockpit.experiment.structuredIllumination as sim

class PostpadTestCase(unittest.TestCase):
    def test_pad_data(self):
        data = numpy.ones((3,), dtype=numpy.uint16)
        padded = sim.postpad_data(data, (10,))
        self.assertEqual(padded.size, 10)
        self.assertEqual(padded.shape, (10,))
        self.assertTrue((padded[[0,2,3,9]] == [1, 1, 0, 0]).all())

        data = numpy.ones((3,), dtype=numpy.double)
        padded = sim.postpad_data(data, (10,))
        self.assertEqual(padded.size, 10)
        self.assertEqual(padded.shape, (10,))
        self.assertTrue((padded[[0,2]] == [1.0, 1.0]).all())
        self.assertTrue((numpy.isnan(padded[[3,9]])).all())

        data = numpy.ones((4,3,5))
        padded = sim.postpad_data(data, (5, 4, 5))
        self.assertEqual(padded.size, 100)
        self.assertEqual(padded.shape, (5, 4, 5))
        self.assertTrue(padded[:4,:3,:5].all())
        self.assertTrue(numpy.isnan(padded[4:,:,:]).all())
        self.assertTrue(numpy.isnan(padded[:,3:,:]).all())

        data = numpy.ones((3,))
        padded = sim.postpad_data(data, (3,))
        self.assertEqual(padded.size, 3)
