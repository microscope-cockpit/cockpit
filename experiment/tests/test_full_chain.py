import unittest
import mock
import decimal
import threading
import traceback
import time
import uuid
import os
import sys
from mockManagers import replace_with_mock, mock_import

def dumpstacks():
    id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
    code = []
    for threadId, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % (id2name.get(threadId,""), threadId))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % (filename, lineno, name))
            if line:
                code.append("  %s" % (line.strip()))
    return "\n".join(code)



class TestChain(unittest.TestCase):


    def setUp(self):

        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig', 'logging',
                          'interfaces', 'interfaces.stageMover',
                          'depot']) as mocks:
            self.mockDepot = mocks['depot']
            import experiment.experiment
            import experiment.structuredIllumination
            import util.logger
            import devices.dummyCamera
            import devices.executor
            util.logger.makeLogger()

        self.experiment = experiment.structuredIllumination.SIExperiment

        config = {'maxFilesizeMegabytes':1e6}

        self.mockDepot.CAMERA = devices.dummyCamera
        self.mockDepot.EXECUTOR = devices.executor.ExperimentExecutorDevice()
        self.mockDepot.CONFIGURATOR = mock.Mock()
        self.mockDepot.CONFIGURATOR.getValue = lambda key: config[key]

        self.mockDepot.getHandlersOfType = lambda kind: [kind]

        # Recreates the basic init for the experiment class.
        self.MockHandler = mock.MagicMock(name='MockHandler')
        self.MockCamera = mock.MagicMock(name='MockCamera')
        self.MockCamera.getTimeBetweenExposures.return_value = decimal.Decimal(0)
        self.MockCamera.getExposureTime.return_value = decimal.Decimal(0)
        self.MockCamera.getImageSize.return_value = (100, 100)
        self.MockLight = mock.MagicMock(name='MockLight')
        self.MockLight.getWavelength.return_value = 650


        self.MockHandler.getSavefileInfo.return_value = ''
        self.MockLight.getSavefileInfo.return_value = ''
        self.MockCamera.getSavefileInfo.return_value = ''


        self.savePath = os.path.join(os.getcwd(), 'experimenttest'+str(uuid.uuid4()))

        self.test_params = {'numReps':1,
                            'repDuration':0,
                            'zPositioner':self.MockHandler,
                            'zBottom':0,
                            'zHeight':0,
                            'sliceHeight':0,
                            'cameras':[self.MockCamera],
                            'lights':[self.MockLight],
                            'exposureSettings':[([self.MockCamera], [(self.MockLight, 0)])],
                            'otherHandlers':[],
                            'metadata':'metadata',
                            'savePath':self.savePath}

        self.test_params['numAngles'] = 5
        self.test_params['collectionOrder'] = "Angle, Phase, Z"
        self.test_params['bleachCompensations'] = mock.MagicMock()
        self.test_params['bleachCompensations'].__getitem__ = lambda *_: 0.1
        self.test_params['sliceHeight'] = 1
        self.test_params['zHeight'] = 2
        self.test_params['zPositioner'].getMovementTime.return_value = (0.1, 0.1)

    def test_chain(self):
        text_expr = self.experiment(**self.test_params)
        text_expr.run()
        time.sleep(1)

        PrevStack = ''
        while threading.activeCount() > 1:
            stack = dumpstacks()
            if stack != PrevStack:
                print(stack)
                print('-'*80)
            PrevStack = stack
            time.sleep(1)
