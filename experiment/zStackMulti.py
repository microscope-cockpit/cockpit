import actionTable
import depot
import experiment

import math



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
            curTime = table.addToggle(curTime, delayGen)
            # Trigger the cameras once. Lazy; only allow one set of cameras.
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



#### Temporarily hacked to vary exposure time as a function of depth.
##class ZStackMultiExperiment(experiment.Experiment):
##    ## Create the ActionTable needed to run the experiment. We simply move to 
##    # each Z-slice in turn, take our image, then move to the next.
##    def generateActions(self):
##        table = actionTable.ActionTable()
##        curTime = 0
##        prevAltitude = None
##        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
##        zCenter = (numZSlices / 2) * self.sliceHeight
##        for zIndex in xrange(numZSlices):
##            # Move to the next position, then wait for the stage to 
##            # stabilize.
##            targetAltitude = self.sliceHeight * zIndex
##            motionTime, stabilizationTime = 0, 0
##            if prevAltitude is not None:
##                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, targetAltitude)
##            table.addAction(curTime + motionTime, self.zPositioner, 
##                    targetAltitude)
##            curTime += motionTime + stabilizationTime            
##            prevAltitude = targetAltitude
##
##            # Image the sample, with exposure time quadrupling for each
##            # micron away from the center of the stack we are.
##            import decimal
##            factor = decimal.Decimal(abs(targetAltitude - zCenter) * 4) + 1
##            factor = [decimal.Decimal('1'), decimal.Decimal('1.1')][zIndex % 2]
##            for cameras, lightTimePairs in self.exposureSettings:
##                newPairs = []
##                for light, duration in lightTimePairs:
##                    newPairs.append((light, duration * factor))
##                curTime = self.expose(curTime, cameras, newPairs, table)
##            # Hold the Z motion flat during the exposure.
##            table.addAction(curTime, self.zPositioner, targetAltitude)
##
##        # Move back to the start so we're ready for the next rep.
##        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
##                self.zHeight, 0)
##        curTime += motionTime
##        table.addAction(curTime, self.zPositioner, 0)
##        # Hold flat for the stabilization time, and any time needed for
##        # the cameras to be ready. Only needed if we're doing multiple
##        # reps, so we can proceed immediately to the next one.
##        cameraReadyTime = 0
##        if self.numReps > 1:
##            for cameras, lightTimePairs in self.exposureSettings:
##                for camera in cameras:
##                    cameraReadyTime = max(cameraReadyTime,
##                            self.getTimeWhenCameraCanExpose(table, camera))
##        table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
##                self.zPositioner, 0)
##
##        return table
