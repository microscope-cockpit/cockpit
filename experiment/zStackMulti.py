import actionTable
import depot
import experiment
import gui.guiUtils
import util.userConfig

import decimal
import math
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = "Multi-exposure Z-stack"



## Just like a standard Z-stack experiment, but we do multiple exposure times
# at each Z slice. Hacked all to hell though since we rely on OMXT's
# delay generator being set up for us ahead of time.
class ZStackMultiExperiment(experiment.Experiment):
    def __init__(self, exposureMultiplier = 10, exposureDelay = 1, *args, **kwargs):
        experiment.Experiment.__init__(self, *args, **kwargs)
        ## Amount to multiply subsequent exposures by.
        self.exposureMultiplier = decimal.Decimal(exposureMultiplier)
        ## Amount of time to wait after the *beginning* of the first exposure
        # before *beginning* the second exposure.
        self.exposureDelay = decimal.Decimal(exposureDelay)

        
    ## Create the ActionTable needed to run the experiment. We simply move to 
    # each Z-slice in turn, take our images, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        # Open all light sources for the duration of the experiment.
        # Normally the delay generator logic would do this for us.
        for cameras, exposures in self.exposureSettings:
            for light, exposureTime in exposures:
                table.addAction(0, light, True)
        shutter = depot.getHandlerWithName('488 shutter')
        delayGen = depot.getHandlerWithName('Delay generator trigger')
        curTime = 0
        table.addAction(curTime, shutter, True)
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        for zIndex in xrange(numZSlices):
            # Move to the next position, then wait for the stage to 
            # stabilize.
            targetAltitude = self.initialZPos + self.sliceHeight * zIndex
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, targetAltitude)
            table.addAction(curTime + motionTime, self.zPositioner, 
                    targetAltitude)
            curTime += motionTime + stabilizationTime            
            prevAltitude = targetAltitude

            # Trigger the delay generator. Do it slightly *after* the trigger
            # of the cameras below, so that we ensure the first exposure, which
            # may be very brief, is fully-contained in a camera exposure.
            table.addToggle(curTime + decimal.Decimal('.5'), delayGen)
            # Trigger the cameras twice. Lazy; only allow one set of cameras.
            cameras = self.exposureSettings[0][0]
            for camera in cameras:
                table.addToggle(curTime, camera)
                table.addToggle(curTime + self.exposureDelay, camera)
                self.cameraToImageCount[camera] += 2
            maxCamDelay = max(c.getTimeBetweenExposures(isExact = True) for c in cameras)
            # Wait for the exposure to complete and/or for the cameras to be
            # ready again.
            longExposureTime = self.exposureSettings[0][1][0][1] * self.exposureMultiplier
            curTime += self.exposureDelay + max(maxCamDelay,
                    self.exposureDelay + longExposureTime)
            # Plus a little extra for the cameras to recover.
            # \todo This seems a bit excessive; why do we need to wait so
            # long for the Zyla to be ready?
            curTime += decimal.Decimal('10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, targetAltitude)

        # Close all light sources we opened at the start.
        # Normally the delay generator logic would do this for us.
        for cameras, exposures in self.exposureSettings:
            for light, exposureTime in exposures:
                table.addAction(curTime, light, False)
                
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
        wx.Panel.__init__(self, parent)
        self.configKey = configKey
        self.settings = self.loadSettings()

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.exposureMultiplier = gui.guiUtils.addLabeledInput(self, 
                sizer, label = "Exposure multiplier",
                defaultValue = self.settings['exposureMultiplier'],
                helperString = "Amount to multiply the normal exposure duration by to get the second exposure duration.")

        self.exposureDelay = gui.guiUtils.addLabeledInput(self,
                sizer, label = "Delay between exposures",
                defaultValue = self.settings['exposureDelay'],
                helperString = "Amount of time to wait, in milliseconds, between the beginning of the first exposure and the beginning of the second exposure. Should be long enough for the camera to recover from taking the first image!")

        self.SetSizerAndFit(sizer)


    ## Given a parameters dict to hand to the experiment instance, augment
    # it with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['exposureMultiplier'] = gui.guiUtils.tryParseNum(
                self.exposureMultiplier, float)
        params['exposureDelay'] = gui.guiUtils.tryParseNum(self.exposureDelay, float)
        return params


    ## Load saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'ZStackMultiSettings',
                default = {
                    'exposureMultiplier': '10',
                    'exposureDelay': '5',
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'exposureMultiplier': self.exposureMultiplier.GetValue(),
                'exposureDelay': self.exposureDelay.GetValue(),
        }


    ## Save current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'ZStackMultiSettings', settings
        )

