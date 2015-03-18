import actionTable
import depot
import experiment
import gui.guiUtils

import math
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = "Multi-exposure Z-stack"



## Just like a standard Z-stack experiment, but we do multiple exposure times
# at each Z slice. Hacked all to hell though since we rely on OMXT's
# delay generator being set up for us ahead of time.
class ZStackMultiExperiment(experiment.Experiment):
    ## Create the ActionTable needed to run the experiment. We simply move to 
    # each Z-slice in turn, take our images, then move to the next.
    def generateActions(self):
        shutter = depot.getHandlerWithName('488 shutter')
        delayGen = depot.getHandlerWithName('Delay generator trigger')
        table = actionTable.ActionTable()
        curTime = 0
        table.addAction(curTime, shutter, True)
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        for zIndex in xrange(numZSlices):
            # Move to the next position, then wait for the stage to 
            # stabilize.
            targetAltitude = self.sliceHeight * zIndex
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, targetAltitude)
            table.addAction(curTime + motionTime, self.zPositioner, 
                    targetAltitude)
            curTime += motionTime + stabilizationTime            
            prevAltitude = targetAltitude

            # Trigger the delay generator.
            table.addToggle(curTime, delayGen)
            # Trigger the cameras twice. Lazy; only allow one set of cameras.
            cameras = self.exposureSettings[0][0]
            for camera in cameras:
                table.addAction(curTime, camera, True)
                table.addAction(curTime + 5, camera, False)
                table.addAction(curTime + 15, camera, True)
                table.addAction(curTime + 20, camera, False)
                self.cameraToImageCount[camera] += 2
            curTime += 25
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, targetAltitude)

        table.addAction(curTime, shutter, False)
        # Move back to the start so we're ready for the next rep.
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        curTime += motionTime
        table.addAction(curTime, self.zPositioner, 0)
        # Hold flat for the stabilization time, and any time needed for
        # the cameras to be ready. Only needed if we're doing multiple
        # reps, so we can proceed immediately to the next one.
        cameraReadyTime = 0
        if self.numReps > 1:
            for cameras, lightTimePairs in self.exposureSettings:
                for camera in cameras:
                    cameraReadyTime = max(cameraReadyTime,
                            self.getTimeWhenCameraCanExpose(table, camera))
        table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
                self.zPositioner, 0)

        return table



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = ZStackMultiExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        self.configKey = configKey
        self.settings = self.loadSettings()

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.exposureMultiplier = gui.guiUtils.addLabeledInput(self, 
                sizer, label = "Exposure multiplier",
                defaultValue = self.settings['exposureMultiplier'],
                helperString = "Amount to multiply the normal exposure duration by to get the second exposure duration.")

        self.delay = gui.guiUtils.addLabeledInput(self,
                sizer, label = "Delay between exposures",
                defaultValue = self.settings['delay'],
                helperString = "Amount of time to wait, in milliseconds, between the end of the first exposure and the beginning of the second exposure.")

        self.SetSizerAndFit(sizer)


    ## Given a parameters dict to hand to the experiment instance, augment
    # it with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        vals = self.getSettingsDict()
        params.update(vals)
        return params


    ## Load saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'ZStackMultiSettings',
                default = {
                    'exposureMultiplier': '10',
                    'delay': '5',
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'exposureMultiplier': gui.guiUtils.tryParseNum(
                    self.exposureMultiplier, float),
                'exposureDelay': gui.guiUtils.tryParseNum(self.delay, float)
        }


    ## Save current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'ZStackMultiSettings', settings
        )

