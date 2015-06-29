import unittest
import mock
import numpy as np
import util.correctNonlinear


class TestCorrector(unittest.TestCase):

    def test_flat(self):
        exposures = np.linspace(0, 10, 6)
        mapData = np.ones((6, 10, 10))

        for i, n in enumerate(exposures):
            mapData[i,:,:] *= n

        corrector = util.correctNonlinear.Corrector(exposures, mapData)
        self.assertAlmostEqual(corrector.slope, 1)
        self.assertAlmostEqual(corrector.intercept, 0)

    def test_correct(self):
        '''Corrector multiplies the corrected data by the global trend to
        rescale th corrected data into the range the camera normally produces.
        For our first order scaled data this means correcting is a no-op.
        '''
        exposures = np.linspace(0, 10, 6)
        mapData = np.ones((6, 10, 10))

        for i, n in enumerate(exposures):
            mapData[i,:,:] = mapData[i,:,:] * (n*2)

        corrector = util.correctNonlinear.Corrector(exposures, mapData)
        print(corrector.slope)
        self.assertTrue(np.allclose(corrector.correct(np.ones((10, 10))*15),
                                    np.ones((10, 10))*15, rtol=1e-4, atol=1e-4))


    def test_correct_multi_rate(self):
        exposures = np.concatenate((np.linspace(0, 1, 5), np.linspace(9, 10, 5)))
        mapData = np.ones((10, 10, 10))

        for i, n in enumerate(exposures):
            mapData[i,:,:] *= n

        midExposures = np.linspace(4, 5, 5)
        midMapData = np.ones((5, 10, 10))

        for i, n in enumerate(midExposures):
            midMapData[i,:,:] *= n/2 + 2

        fullExposures = np.concatenate((exposures, midExposures))
        fullMapData = np.concatenate((mapData, midMapData))

        print(len(fullExposures), len(fullMapData))
        corrector = util.correctNonlinear.Corrector(fullExposures, fullMapData)
        # 3 parts + 2 linear interps.
        self.assertEqual(len(corrector.subCorrectors), 5)
