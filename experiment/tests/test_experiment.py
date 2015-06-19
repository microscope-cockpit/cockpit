'''Huge integration test that creates a example experiment and ensures
data is captured and written.

do one massive setup, and then tests are that individual classes were used
correctly.
'''
import unittest
import mock
import uuid
import subprocess
import os
import decimal
import threading

import experiment.experiment
import experiment.actionTable

class TestExperiment(unittest.TestCase):

    def setUp(self):
        # Recreates the basic init for the experiment class.
        self.MockHandler = mock.MagicMock()
        self.MockCamera = mock.MagicMock()
        self.MockCamera.getTimeBetweenExposures.return_value = decimal.Decimal(0)
        self.MockCamera.getExposureTime.return_value = decimal.Decimal(0)
        self.MockCamera.getImageSize.return_value = (0, 0)
        self.MockLight = mock.MagicMock()
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


    def tearDown(self):
        if self.savePath:
            # remove any temp files
            subprocess.Popen(['rm', self.savePath]).wait()
            # For splitting, files are created with savePath.NNN
            subprocess.Popen(['rm', self.savePath+'.*']).wait()


    def test___init__(self):
        '''Test that no exceptions are raised.'''
        experiment.experiment.Experiment(**self.test_params)


    def test_non_decimal_readout(self):
        '''The value the handler produces must be a decimal.Decimal - test that
        the experiment checks this.
        '''
        self.MockCamera.getTimeBetweenExposures.return_value = 0
        with mock.patch('experiment.experiment.interfaces.stageMover'):
            test_exp = experiment.experiment.Experiment(**self.test_params)
            self.assertRaises(RuntimeError, test_exp.run)


    def test_broken_handlers(self):
        pass
        #boo


    def test_zstack_return_value(self):
        import experiment.zStack
        import experiment.actionTable

        # We don't need to move a stage
        with mock.patch('experiment.experiment.interfaces.stageMover'):
            # As this is a z-experiment, give some height
            self.test_params['zHeight'] = 5
            self.test_params['sliceHeight'] = 1
            self.test_params['savePath'] = ''

            # The z handler mock needs to have some behaviour. (movetime, stabilize)
            self.test_params['zPositioner'].getMovementTime.return_value = (0, 0)

            test_experiment = experiment.zStack.ZStackExperiment(**self.test_params)
            test_experiment.run()
            test_experiment.cleanup()


    def test_emtpy_save_path_does_not_call_dataSaver(self):
        self.test_params['savePath'] = ''
        with mock.patch('experiment.experiment.interfaces.stageMover'):
            with mock.patch('experiment.experiment.dataSaver') as ds:

                test_exp = experiment.experiment.Experiment(**self.test_params)
                test_exp.generateActions = mock.MagicMock()
                test_exp.run()
                self.assertFalse(ds.called)


if __name__ == '__main__':
    unittest.main()
