import actionTable
import experiment

import decimal
import math

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Z-stack'


## This class handles classic Z-stack experiments.
class ZStackExperiment(experiment.Experiment):
    ## Create the ActionTable needed to run the experiment. We simply move to 
    # each Z-slice in turn, take an image, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        if self.zHeight > 1e-6:
            # Non-2D experiment; tack on an extra image to hit the top of
            # the volume.
            numZSlices += 1
        for zIndex in xrange(numZSlices):
            # Move to the next position, then wait for the stage to 
            # stabilize.
            targetAltitude = self.initialZPos + self.sliceHeight * zIndex
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, targetAltitude)
            curTime += motionTime
            table.addAction(curTime, self.zPositioner, targetAltitude)
            curTime += stabilizationTime
            prevAltitude = targetAltitude

            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('1e-10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, targetAltitude)

        # Move back to the start so we're ready for the next rep.
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        curTime += motionTime
        table.addAction(curTime, self.zPositioner, self.initialZPos)
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
                self.zPositioner, self.initialZPos)

        return table



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = ZStackExperiment
