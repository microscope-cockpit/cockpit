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
    def __init__(self, angleHandler = None, settlingTime=0.1, *args, **kwargs):
        experiment.Experiment.__init__(self, *args, **kwargs)
        self.angleHandler = angleHandler
        self.settlingTime = settlingTime


    ## Create the ActionTable needed to run the experiment. We simply move to 
    # each Z-slice in turn, take an image, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        numZSlices = 1
        vLessThan = 10.
        vStart = 0.
        vSteps = 100
        dv = (vLessThan - vStart) / vSteps
        dt = decimal.Decimal(self.settlingTime)

        for step in xrange(vSteps):
            # Move to next polarization rotator voltage.
            vTarget = vStart + step * dv
            table.addAction(curTime + dt, self.angleHandler, 
                    vTarget)
            curTime += dt
            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('1e-10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.angleHandler, vTarget)

        return table


## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = RotatorSweepExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)
        self.configKey = configKey
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        ## Maps strings to TextCtrls describing how to configure 
        # response curve experiments.
        self.settings = self.loadSettings()
        self.responseArgs = {}
        self.settlingTimeControl = gui.guiUtils.addLabeledInput(
                                        self, sizer, label='settling time',
                                        defaultValue=self.settings['settlingTime'],)
        sizer.Add(self.settlingTimeControl)
        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['settlingTime'] = gui.guiUtils.tryParseNum(self.settlingTimeControl)
        params['angleHandler'] = depot.getHandlerWithName('SI angle')
        return params        


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'settlingTime',
                default = {
                    'settlingTime': '0.1', 
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'settlingTime': self.settlingTimeControl.GetValue(),}


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'settlingTime',
                settings)
