'''DataSaver is very fragile, and tightly coupled!

Even if we can't get a good idea of functional correctness, we can make sure
the module all compiles and works.

It also uses it's own threads, and so currently does not
die at the end of the test run.


'''

import unittest
import threading
import mock
from experiment import dataSaver
DataSaver = dataSaver.DataSaver

from handlers import camera
import os
import inspect
import subprocess
import uuid

class TestDataSaver(unittest.TestCase):

    def setUp(self):
        self.depot = mock.MagicMock()
        self.camera = mock.MagicMock()
        self.camera.getImageSize.return_value = (0, 0)
        self.cameraToImagesPerRep = mock.MagicMock()
        self.cameraToIgnoredImageIndices = mock.MagicMock()
        # Give each file a random name to delete later
        self.savePath = os.path.join(os.getcwd(), 'datasavertestfile'+str(uuid.uuid4()))

        dataSaver.depot = mock.MagicMock()
        self.data_saver = DataSaver(cameras=[self.camera],
                                    numReps=0,
                                    cameraToImagesPerRep=self.cameraToImagesPerRep,
                                    cameraToIgnoredImageIndices=self.cameraToIgnoredImageIndices,
                                    runThread=None,
                                    savePath=self.savePath,
                                    pixelSizeZ=None,
                                    titles=[])

    def tearDown(self):
        subprocess.Popen(['rm', self.savePath]).wait()


    def test___init__(self):
        '''Absolutely minimal class instance.
        '''
        self.assertTrue(isinstance(self.data_saver, DataSaver))


    def test_opens_correct_file(self):
        '''Tests that executeAndSave uses the right file.
        using a Mock insted of a real instance for simplicity.
        '''
        # OH MY.
        #for attr, value in inspect.getmembers(self.data_saver):
        #    exec()
        #self.data_saver
        #DataSaver.executeAndSave(dsMock)
        pass

        '''
    def test_cleanup(self):
        assert False # TODO: implement your test here

    def test_executeAndSave(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.executeAndSave())
        assert False # TODO: implement your test here

    def test_getFilenames(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.getFilenames())
        assert False # TODO: implement your test here

    def test_onAbort(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.onAbort())
        assert False # TODO: implement your test here

    def test_onImage(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.onImage(cameraIndex, imageData, timestamp))
        assert False # TODO: implement your test here

    def test_saveData(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.saveData())
        assert False # TODO: implement your test here
        '''
        ## startCollecting opens a new thread that keeps the tests alive indef.
        '''
    def test_startCollecting(self):
        mock_camera = mock.MagicMock()
        self.statusThread = mock.MagicMock()
        self.data_saver.cameras = [mock_camera]
        dataSaver.events = mock.MagicMock()
        self.data_saver.startCollecting()
        print(mock_camera.call_args_list)
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.startCollecting())
        '''

        '''
    def test_writeImage(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.writeImage(cameraIndex, imageData, timestamp))
        assert False # TODO: implement your test here


    def test_executeAndSave(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.executeAndSave())
        assert False # TODO: implement your test here

    def test_getFilenames(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.getFilenames())
        assert False # TODO: implement your test here

    def test_onAbort(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.onAbort())
        assert False # TODO: implement your test here

    def test_onImage(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.onImage(cameraIndex, imageData, timestamp))
        assert False # TODO: implement your test here

    def test_saveData(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.saveData())
        assert False # TODO: implement your test here

    def test_startCollecting(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.startCollecting())
        assert False # TODO: implement your test here

    def test_writeImage(self):
        # data_saver = DataSaver(cameras, numReps, cameraToImagesPerRep, cameraToIgnoredImageIndices, runThread, savePath, pixelSizeZ, titles)
        # self.assertEqual(expected, data_saver.writeImage(cameraIndex, imageData, timestamp))
        assert False # TODO: implement your test here

class TestStatusUpdateThread(unittest.TestCase):
    def test___init__(self):
        # status_update_thread = StatusUpdateThread(cameraNames, totals)
        assert False # TODO: implement your test here

    def test_newImage(self):
        # status_update_thread = StatusUpdateThread(cameraNames, totals)
        # self.assertEqual(expected, status_update_thread.newImage(index))
        assert False # TODO: implement your test here

    def test_run(self):
        # status_update_thread = StatusUpdateThread(cameraNames, totals)
        # self.assertEqual(expected, status_update_thread.run())
        assert False # TODO: implement your test here

    def test_updateText(self):
        # status_update_thread = StatusUpdateThread(cameraNames, totals)
        # self.assertEqual(expected, status_update_thread.updateText())
        assert False # TODO: implement your test here
        '''
if __name__ == '__main__':
    unittest.main()
