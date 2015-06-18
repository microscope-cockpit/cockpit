import unittest
import colors
import numpy as np

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
