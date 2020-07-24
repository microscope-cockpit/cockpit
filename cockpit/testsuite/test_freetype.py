#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import cockpit.gui.freetype


class FaceTestCase(unittest.TestCase):
    def setUp(self):
        self.face = cockpit.gui.freetype.Face(18)

    def test_render(self):
        ## Not sure how to actual test if it gets rendered, but this
        ## should at least not error.
        self.face.render('foobar')
