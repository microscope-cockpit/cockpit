import depot
import device
import events
import handlers.executor
import interfaces.imager
import interfaces.stageMover

import time

CLASS_NAME = 'ExperimentExecutorDevice'



## This experiment executor simply performs each step in the experiment
# manually.
class ExperimentExecutorDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.shouldAbort = False


    def initialize(self):
        events.subscribe('user abort', self.onAbort)

    
    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.ExecutorHandler(
            "Default experiment executor", "executor",
            {'examineActions': self.examineActions, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable})]


    ## User clicked the abort button; stop our experiment execution, if
    # applicable.
    def onAbort(self):
        self.shouldAbort = True


    ## Given an experiment.ActionTable instance, examine the actions and 
    # make any necessary modifications.
    def examineActions(self, name, table):
        pass


    ## Figure out how many lines of the provided table we can execute on our
    # own, starting from the specified index. We can execute all camera, light,
    # and stage motion actions.
    def getNumRunnableLines(self, name, table, curIndex):
        total = 0
        for time, handler, action in table[curIndex:]:
            if handler.deviceType in [depot.CAMERA, depot.LIGHT_TOGGLE, depot.STAGE_POSITIONER]:
                total += 1
            else:
                return total
        return total


    ## Execute the table of experiment actions.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        activeLights = filter(lambda l: l.getIsEnabled(), allLights)
        # Pre-emptively disable all lights.
        for light in activeLights:
            light.setEnabled(False)
        allCameras = depot.getHandlersOfType(depot.CAMERA)
        curPosition = interfaces.stageMover.getPosition()
        for repNum in xrange(numReps):
            if self.shouldAbort:
                break
            startTime = time.time()
            curTime = startTime
            
            for i, (eventTime, handler, action) in enumerate(table[startIndex:stopIndex]):
                if self.shouldAbort:
                    break
                timeOffset = time.time() - startTime
                if action and handler.deviceType == depot.CAMERA:
                    # Rising edge of a camera trigger: scan until the falling
                    # edge to find what light sources are involved.
                    lightToTriggerTime = {}
                    lightToExposureTime = {}
                    for j, (altTime, altHandler, altAction) in enumerate(table[i + 1:stopIndex]):
                        if altHandler in allLights:
                            if altAction:
                                # Starting an exposure.
                                lightToTriggerTime[altHandler] = altTime
                            else:
                                # Ending an exposure; record the exposure time.
                                # Paranoia: if we don't have a start time for
                                # the exposure, then use the camera trigger time.
                                startTime = lightToTriggerTime.get(altHandler, eventTime)
                                lightToExposureTime[altHandler] = altTime - startTime
                        if altHandler is handler and not altAction:
                            # Ending camera trigger; set its exposure time.
                            exposureTime = altTime - eventTime
                            handler.setExposureTime(exposureTime)
                            break
                    # Set the exposure time for each active light source.
                    for light, triggerTime in lightToTriggerTime.iteritems():
                        light.setEnabled(True)
                        # Use the light's true exposure time if available;
                        # otherwise, end the exposure with the camera.
                        exposureTime = lightToExposureTime.get(light, eventTime - triggerTime)
                        # Cast to float (i.e. away from Decimal).
                        light.setExposureTime(float(exposureTime))
                    interfaces.imager.takeImage(shouldBlock = True)
                    for light in lightToExposureTime.keys():
                        light.setEnabled(False)
                elif handler.deviceType == depot.STAGE_POSITIONER:
                    # Positioning is specified relative to our starting
                    # position.
                    target = list(curPosition)
                    target[handler.axis] += action
                    interfaces.stageMover.goTo(target, shouldBlock = False)
                eventTime = float(eventTime)
                targetTime = startTime + (eventTime / 1000)
                time.sleep(max(0, targetTime - curTime))
                curTime = time.time()
                
            if repDuration is not None:
                # Wait out the remaining rep time.
                # Convert repDuration from milliseconds to seconds.
                waitTime = (repDuration / 1000) - (time.time() - startTime)
                time.sleep(max(0, waitTime))
        # Return the lights to the enabled/disabled status they had at the
        # start of execution.
        for light in allLights:
            light.setEnabled(light in activeLights)
        events.publish("experiment execution")
