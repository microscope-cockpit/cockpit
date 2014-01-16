import actionTable
import experiment

import math

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Open-shutter sweep'


## This class handles open-shutter sweep experiments, where we move the sample
# continuously while exposing.
class OpenShutterSweepExperiment(experiment.Experiment):
    ## Create the ActionTable needed to run the experiment. We simply start
    # an exposure at the bottom of the "stack" and end it at the top.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        for cameras, lightTimePairs in self.exposureSettings:
            # Start the stage at the bottom.
            table.addAction(curTime, self.zPositioner, 0)
            # Ensure our exposure is at least as long as the time needed to 
            # move through the sample.
            motionTime, stabilizationTime = self.zPositioner.getMovementTime(0,
                    self.zHeight)
            # Image the sample.
            curTime = self.expose(curTime, cameras, lightTimePairs, table, motionTime)
        
            # End the exposure with the stage at the top.
            table.addAction(curTime, self.zPositioner, self.zHeight)
            curTime += stabilizationTime
            # Move back to the start so we're ready for the next set of cameras
            # or the next rep.
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
                table.addAction(
                        max(curTime + stabilizationTime, cameraReadyTime),
                        self.zPositioner, 0)

        return table


    def expose(self, curTime, cameras, lightTimePairs, motionTime):
        return curTime



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = OpenShutterSweepExperiment
