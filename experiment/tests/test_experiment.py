'''Huge integration test that creates a example experiment and ensures
data is captured and written.

do one massive setup, and then tests are that individual classes were used
correctly.
'''
import unittest
import mock
from contextlib import contextmanager
import inspect
import uuid
import subprocess
import os
import decimal
import threading

import experiment.experiment
import experiment.actionTable

@contextmanager
def replace_with_mock(namespace, funcname):
    '''Replaces a name in the given namespace with a magic mock object.

    with replace_with_mock(namespace, funcname):
        *do whatever with the mock*

    and the namespace is restored here!
    '''
    func_backup = vars(namespace)[funcname]
    vars(namespace)[funcname] = mock.MagicMock()
    print('replacing', funcname)
    yield vars(namespace)[funcname]
    # and restore afterwards
    print('restoring', funcname)
    vars(namespace)[funcname] = func_backup


class TestExperiment(unittest.TestCase):

    def setUp(self):

        # Capture log messages
        experiment.experiment.util.logger = mock.MagicMock()

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
            subprocess.Popen(['rm', '-f', self.savePath]).wait()
            # For splitting, files are created with savePath.NNN
            subprocess.Popen(['rm', '-f', self.savePath+'.*']).wait()


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


    def test_asks_user_when_path_exists(self):
        '''Test that when running the experiment it will ask for confirmation
        before overwriting files.
        '''
        # Create file - will be cleaned up by teardown.
        open(self.savePath, 'w').close()
        with replace_with_mock(experiment.experiment, 'gui') as mockgui:
            mockgui.guiUtils.getUserPermission.return_value = False
            print(mockgui)
            test_exper = experiment.experiment.Experiment(**self.test_params)
            test_exper.run()
            self.assertTrue(mockgui.guiUtils.getUserPermission.called)


    def test_execute_abort(self):
        '''
        The execure has a nasty race in it where you can call
        execute, and then as the thread spins up call abort but execute will
        clear the abort.

        use a infinite generator for table to keep execute spinning, and
        send a syncronus abort to test.
        '''
        # TODO
        with replace_with_mock(experiment.experiment.util, 'logger') as mocklog:
            with replace_with_mock(experiment.experiment, 'depot') as mockdepot:
                with replace_with_mock(experiment.experiment, 'threading'):
                    executor = mock.Mock()
                    executor.getNumRunnableLines.return_value = 1

                    mockdepot.getHandlersOfType = mock.Mock(return_value=[executor])

                    test_exper = experiment.experiment.Experiment(**self.test_params)

                    # execute will keep going as long as the current point is less
                    # than the len of the actiontable - so create a object larger
                    # than any number and return that as the len.
                    def __cmp__(self):
                        return True

                    greatest_number = mock.MagicMock()
                    greatest_number.__cmp__ = __cmp__

                    test_exper.table = mock.MagicMock()
                    test_exper.table.__len__.return_value = greatest_number

                    test_exper.onAbort()
                    #test_exper.execute()


    def test_stuttered_zstack(self):
        import experiment.stutteredZStack
        with mock.patch('experiment.experiment.interfaces.stageMover'):
            with replace_with_mock(experiment.experiment, 'threading'):
                # As this is a z-experiment, give some height
                self.test_params['zHeight'] = 5
                self.test_params['sliceHeight'] = 1
                self.test_params['savePath'] = ''

                # The z handler mock needs to have some behaviour. (movetime, stabilize)
                self.test_params['zPositioner'].getMovementTime.return_value = (0, 0)

                test_experiment = experiment.stutteredZStack.StutteredZStackExperiment(**self.test_params)
                test_experiment.run()
                test_experiment.cleanup()


    def test_zstack(self):
        import experiment.zStack

        # We don't need to move a stage
        with replace_with_mock(experiment.experiment.interfaces, 'stageMover'):
            with replace_with_mock(experiment.experiment, 'threading'):
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
                with replace_with_mock(experiment.experiment, 'threading'):
                    test_exp = experiment.experiment.Experiment(**self.test_params)
                    test_exp.generateActions = mock.MagicMock()
                    test_exp.run()
                    self.assertFalse(ds.called)


if __name__ == '__main__':
    unittest.main()
