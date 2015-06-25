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
import types

from mockManagers import replace_with_mock, mock_import

import experiment.experiment


class TestExperiment(unittest.TestCase):

    def setUp(self):

        # Capture log messages

        self.loggerbackup = experiment.experiment.util.logger
        experiment.experiment.util.logger = mock.MagicMock()

        # Recreates the basic init for the experiment class.
        self.MockHandler = mock.MagicMock(name='MockHandler')
        self.MockCamera = mock.MagicMock(name='MockCamera')
        self.MockCamera.getTimeBetweenExposures.return_value = decimal.Decimal(0)
        self.MockCamera.getExposureTime.return_value = decimal.Decimal(0)
        self.MockCamera.getImageSize.return_value = (0, 0)
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


    def tearDown(self):
        if self.savePath:
            # remove any temp files
            subprocess.Popen(['rm', '-f', self.savePath]).wait()
            # For splitting, files are created with savePath.NNN
            subprocess.Popen(['rm', '-f', self.savePath+'.*']).wait()
        experiment.experiment.util.logger = self.loggerbackup


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
            test_exper = experiment.experiment.Experiment(**self.test_params)
            test_exper.run()
            self.assertTrue(mockgui.guiUtils.getUserPermission.called)


    def test_execute_abort(self):
        '''
        The execute has a nasty race in it where you can call
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
        with mock_import(['util.userConfig']):
            import experiment.stutteredZStack
            with mock.patch('experiment.experiment.interfaces.stageMover'):
                with replace_with_mock(experiment.experiment, 'threading'):
                    # As this is a z-experiment, give some height
                    self.test_params['zHeight'] = 5
                    self.test_params['sliceHeight'] = 1
                    self.test_params['savePath'] = ''

                    # The z handler mock needs to have some behaviour. (movetime, stabilize)
                    self.test_params['zPositioner'].getMovementTime.return_value = (0, 0)

                    test_experiment = experiment.stutteredZStack.StutteredZStackExperiment((0, 0), **self.test_params)
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
        '''Tests that if no file is specified, no saving is attempted.'''
        self.test_params['savePath'] = ''
        with mock.patch('experiment.experiment.interfaces.stageMover'):
            with mock.patch('experiment.experiment.dataSaver') as ds:
                with replace_with_mock(experiment.experiment, 'threading'):
                    test_exp = experiment.experiment.Experiment(**self.test_params)
                    test_exp.generateActions = mock.MagicMock()
                    test_exp.run()
                    self.assertFalse(ds.called)


    def test_sweptShutter(self):
        '''Tests simple swept shutter experiment.

        BUG: expose takes diffrent args. corrected on a different branch.
        '''
        import experiment.sweptShutter
        self.test_params['zPositioner'].getMovementTime.return_value = (0, 0)
        self.test_params['exposureSettings'] = [[self.MockCamera, (self.MockLight, 0)],
                                                [self.MockCamera, (self.MockLight, 0)]]

        test_experiment = experiment.sweptShutter.OpenShutterSweepExperiment(**self.test_params)

        table = test_experiment.generateActions()
        self.assertEqual(len(table), len(self.test_params['exposureSettings']))
        print(table)


    def set_SI_testparams(self):
            '''More parameters are needed for the SI experiments.'''
            self.test_params['numAngles'] = 5
            self.test_params['collectionOrder'] = "Angle, Phase, Z"
            self.test_params['bleachCompensations'] = mock.MagicMock()
            self.test_params['bleachCompensations'].__getitem__ = lambda *_: 0.1
            self.test_params['sliceHeight'] = 1
            self.test_params['zHeight'] = 2
            self.test_params['zPositioner'].getMovementTime.return_value = (0.1, 0.1)


    def test_SI___init__(self):
        '''Test that SI init's without exceptions.
        '''
        with mock_import(['util.userConfig', 'gui.guiUtils']):
            import experiment.structuredIllumination
            self.set_SI_testparams()
            test_exper = experiment.structuredIllumination.SIExperiment(**self.test_params)


    def test_SI_generateActions(self):
        '''Tests the action table generated by the SI experiment.

        With this set of parameters, 452 actions are generated.

        This randomly fails with a decimal + float addition error?
        '''
        with mock_import(['util.userConfig', 'gui.guiUtils']):
            import experiment.structuredIllumination
            self.set_SI_testparams()
            test_exper = experiment.structuredIllumination.SIExperiment(**self.test_params)
            test_exper.cameraToReadoutTime[self.MockCamera] = 0
            action_table = test_exper.generateActions()

        #print(action_table)
        self.assertEqual(len(action_table), 452)


    def test_SI_cleanup_out_of_order(self):
        # The logic for writing out is complex
        pass
        '''
        with mock_import('util.userConfig'), mock_import('gui.guiUtils'), mock_import('util.datadoc'):
            self.set_SI_testparams()
            test_exper = experiment.structuredIllumination.SIExperiment(**self.test_params)
            test_exper.cleanup()
        '''


    def test_response_map(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig',
                          'depot']):
            import experiment.responseMap
            self.test_params['numExposures'] = 5
            self.test_params['exposureTimes'] = [1, 2, 3, 4, 5]
            self.test_params['cosmicRayThreshold'] = 5
            self.test_params['shouldPreserveIntermediaryFiles'] = False
            test_exper = experiment.responseMap.ResponseMapExperiment(**self.test_params)
            test_exper.run()


    def test_response_map_save(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig',
                          'depot',
                          'interfaces.stageMover']) as importedmocks:
            import experiment.responseMap

            importedmocks['depot'].getHandlersOfType.return_value = [1, 2, 3]
            self.test_params['numExposures'] = 5
            self.test_params['exposureTimes'] = [1, 2, 3, 4, 5]
            self.test_params['cosmicRayThreshold'] = 5
            self.test_params['shouldPreserveIntermediaryFiles'] = False
            test_exper = experiment.responseMap.ResponseMapExperiment(**self.test_params)
            test_exper.timesAndImages = mock.MagicMock()
            test_exper.timesAndImages.__len__ = lambda _: 0
            test_exper.save()


    def test_offset_gain(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig',
                          'depot']):
            self.test_params['numExposures'] =  1
            import experiment.offsetGainCorrection
            test_exper = experiment.offsetGainCorrection.OffsetGainCorrectionExperiment(**self.test_params)
            test_exper.run()


    def test_immediate_mode(self):
        import experiment.immediateMode
        test_exper = experiment.immediateMode.ImmediateModeExperiment(1, 1, 1)
        test_exper.run()


    def test_experiment_reg(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig']):
            import experiment.experimentRegistry
            experiments = experiment.experimentRegistry.getExperimentModules()
            self.assertTrue(hasattr(experiments, '__getitem__'))


    def test_experiment_reg(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig']):
            import experiment.experimentRegistry
            experiments = experiment.experimentRegistry.getExperimentModules()
            for experiment in experiments:
                self.assertEqual(type(experiment), types.ModuleType)


    def test_experiment_reg(self):
        with mock_import(['gui.guiUtils',
                          'gui.imageSequenceViewer',
                          'gui.progressDialog',
                          'util.userConfig']):
            import experiment.experimentRegistry
            mockmodule = mock.Mock()
            experiments = experiment.experimentRegistry.registerModule(mockmodule)
            self.assertEqual(experiment.experimentRegistry.getExperimentModules()[-1],
                             mockmodule)

if __name__ == '__main__':
    unittest.main()
