#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import os
import unittest

import cockpit.gui
import cockpit.util.ftgl

class TextureFontTestCase(unittest.TestCase):
    def setUp(self):
        self.font = cockpit.util.ftgl.TextureFont(cockpit.gui.FONT_PATH)

    def test_missing_font(self):
        with self.assertRaisesRegex(RuntimeError, 'failed to create texture'):
            cockpit.util.ftgl.TextureFont('not-a-real-file.ttf')

    def test_set_get_size(self):
        self.assertEqual(self.font.getFaceSize(), 0)
        self.font.setFaceSize(18)
        self.assertEqual(self.font.getFaceSize(), 18)

    def test_render(self):
        ## Not sure how to actual test if it gets rendered, but this
        ## should at least not error.
        self.font.setFaceSize(18)
        self.font.render('foobar')
