import mock
import inspect
import os
import sys
sys.path.append(os.getcwd())


import experiment.dataSaver as dataSaver

depot = mock.MagicMock()
camera = mock.MagicMock()
camera.getImageSize.return_value = (0, 0)
cameraToImagesPerRep = mock.MagicMock()
cameraToIgnoredImageIndices = mock.MagicMock()
savePath = os.path.join(os.getcwd(), 'testfile')

depot = dataSaver.depot
dataSaver.depot = mock.MagicMock()
data_saver = dataSaver.DataSaver(cameras=[camera],
                                 numReps=0,
                                 cameraToImagesPerRep=cameraToImagesPerRep,
                                 cameraToIgnoredImageIndices=cameraToIgnoredImageIndices,
                                 runThread=None,
                                 savePath=savePath,
                                 pixelSizeZ=None,
                                 titles=[])
