#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import cockpit.util.colors as colors


class TestWavelengthToColor(unittest.TestCase):
    def test_wavelenth_to_color_red(self):
        R, G, B = colors.wavelengthToColor(650)
        self.assertEqual(G, 0)
        self.assertEqual(B, 0)
        self.assertGreater(R, 0)

    def test_wavelenth_to_color_blue(self):
        R, G, B = colors.wavelengthToColor(410)
        self.assertEqual(G, 0)
        self.assertEqual(R, 0)
        self.assertGreater(B, 0)

    def test_wavelenth_to_color_no_color(self):
        with self.assertRaises(TypeError):
            colors.wavelengthToColor(None)


class TestHsvToRgb(unittest.TestCase):
    def test_hsv_to_rgb_greyscale(self):
        v = 1
        self.assertEqual((v, v, v), colors.hsvToRgb(0, 0, v))

    def test_hsv_to_rgb_full_saturation_red(self):
        R = colors.hsvToRgb(0, 1, 1)
        self.assertEqual((1, 0, 0), R)

    def test_hsv_to_rgb_full_saturation_green(self):
        G = colors.hsvToRgb(120, 1, 1)
        self.assertEqual((0, 1, 0), G)

    def test_hsv_to_rgb_full_saturation_blue(self):
        G = colors.hsvToRgb(240, 1, 1)
        self.assertEqual((0, 0, 1), G)


if __name__ == '__main__':
    unittest.main()
