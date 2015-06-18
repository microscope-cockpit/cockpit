import unittest
import colors
import numpy as np

class TestWavelengthToColor(unittest.TestCase):

    def test_wavelenth_to_color_red(self):
        R, G, B = colors.wavelengthToColor(650)
        self.assertEqual(G, 0)
        self.assertEqual(B, 0)
        self.assertGreater(R, 0)

    def test_wavelenth_to_color_blue(self):
        R, G, B = colors.wavelengthToColor(400)
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
