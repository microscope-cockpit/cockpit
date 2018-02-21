import actionTable
import depot
import experiment
import gui
import util

import decimal
import math
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'RotatorSweep'


## This class handles classic Z-stack experiments.
class RotatorSweepExperiment(experiment.Experiment):
    def __init__(self, polarizerHandler=None, settlingTime=0.1,
                 startV=0.0, maxV=10., vSteps=100, *args, **kwargs):
        experiment.Experiment.__init__(self, *args, **kwargs)
        self.polarizerHandler = polarizerHandler
        self.settlingTime = settlingTime
        # Look up the rotator analogue line handler.
        self.lineHandler = polarizerHandler.getLineHandler()
        self.vRange = (startV, maxV, vSteps)
        vDelta = float(maxV - startV) / vSteps
        # Add voltage parameters to the metadata.
        self.metadata = 'Rotator start and delta: [%f, %f]' % (startV, vDelta)


    ## Create the ActionTable needed to run the experiment.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        vStart, vLessThan, vSteps = self.vRange
        dv = float(vLessThan - vStart) / float(vSteps)
        dt = decimal.Decimal(self.settlingTime)

        for step in xrange(vSteps):
            # Move to next polarization rotator voltage.
            vTarget = vStart + step * dv
            table.addAction(curTime, self.lineHandler, vTarget)
            curTime += dt
            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('.001')
            # Hold the rotator angle constant during the exposure.
            table.addAction(curTime, self.lineHandler, vTarget)
            # Advance time slightly so all actions are sorted (e.g. we
            # don't try to change angle and phase in the same timestep).
            curTime += dt

        return table


## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = RotatorSweepExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)
        self.configKey = configKey
        sizer = wx.GridSizer(2, 4, 1)
        ## Maps strings to TextCtrls describing how to configure
        # response curve experiments.
        self.settings = self.loadSettings()
        self.settlingTimeControl = gui.guiUtils.addLabeledInput(
                                        self, sizer, label='settling time',
                                        defaultValue=self.settings['settlingTime'],)
        sizer.Add(self.settlingTimeControl)
        self.vStepsControl = gui.guiUtils.addLabeledInput(
                                        self, sizer, label='V steps',
                                        defaultValue=self.settings['vSteps'],)
        sizer.Add(self.vStepsControl)
        self.startVControl = gui.guiUtils.addLabeledInput(
                                        self, sizer, label='V start',
                                        defaultValue=self.settings['startV'],)
        sizer.Add(self.startVControl)
        self.maxVControl = gui.guiUtils.addLabeledInput(
                                        self, sizer, label='V max',
                                        defaultValue=self.settings['maxV'],)
        sizer.Add(self.maxVControl)
        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['settlingTime'] = gui.guiUtils.tryParseNum(self.settlingTimeControl, float)
        params['startV'] = gui.guiUtils.tryParseNum(self.startVControl, float)
        params['maxV'] = gui.guiUtils.tryParseNum(self.maxVControl, float)
        params['vSteps'] = gui.guiUtils.tryParseNum(self.vStepsControl)
        params['polarizerHandler'] = depot.getHandlerWithName('SI polarizer')
        return params


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'RotatorSweepExperimentSettings',
                default = {
                    'settlingTime': '0.1',
                    'startV' : '0.0',
                    'maxV': '10.0',
                    'vSteps': '100',
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return  {
                'settlingTime': self.settlingTimeControl.GetValue(),
                'startV': self.startVControl.GetValue(),
                'maxV': self.maxVControl.GetValue(),
                'vSteps': self.vStepsControl.GetValue(),}


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'RotatorSweepExperimentSettings',
                settings)
