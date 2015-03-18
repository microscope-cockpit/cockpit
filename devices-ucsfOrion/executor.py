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

            # Track when lights are triggered so we can set their exposure
            # times properly.
            # HACK: we ignore camera events in this executor! We treat
            # end-of-light-exposure as equivalent to snapping an image, since
            # the lights (and their associated emission filters) determine
            # when images are taken anyway. 
            lightToTriggerTime = {}
            
            for i, (eventTime, handler, action) in enumerate(table[startIndex:stopIndex]):
                if self.shouldAbort:
                    break
                timeOffset = time.time() - startTime
                if handler.deviceType == depot.LIGHT_TOGGLE:
                    # Turning a light on/off; track its trigger time or
                    # take an image.
                    if action:
                        # Light turning on.
                        lightToTriggerTime[handler] = eventTime
                    else:
                        # Light turning off; take an image with that light.
                        handler.setEnabled(True)
                        handler.setExposureTime(float(eventTime - lightToTriggerTime[handler]))
                        interfaces.imager.takeImage(shouldBlock = False)
                        handler.setEnabled(False)
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
