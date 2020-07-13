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

import tempfile
import unittest

import numpy
import numpy.testing

from cockpit.util import datadoc


class TestWriteDataAsMrc(unittest.TestCase):
    def setUp(self):
        self.data = numpy.array(range(256), dtype=numpy.uint8).reshape((16, 16))

    def assertWriteAndReadingBack(self):
        with tempfile.NamedTemporaryFile() as fh:
            datadoc.writeDataAsMrc(self.data, fh.name)
            doc = datadoc.DataDoc(fh.name)
        numpy.testing.assert_equal(doc.getImageArray().squeeze(), self.data)

    def test_write_and_read(self):
        """writeDataAsMRC can read back what it writes"""
        self.assertWriteAndReadingBack()

    def test_not_c_contiguous(self):
        """writeDataAsMRC can handle data that is not C-contiguous"""
        # Some transformations will put the data in non C-contiguous
        # order (see issue #645) so test that we can handle it.
        self.data = numpy.flipud(numpy.rot90(self.data))
        # We could just copy the data in F-contiguous order but doing
        # the transformations shows how cockpit would get to them.
        self.assertFalse(self.data.flags['C_CONTIGUOUS'])
        self.assertWriteAndReadingBack()


if __name__ == '__main__':
    unittest.main()
