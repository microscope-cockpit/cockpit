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

    
    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.ExecutorHandler(
            "Default experiment executor", "executor",
            {'examineActions': self.examineActions, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable})]


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
        allCameras = depot.getHandlersOfType(depot.CAMERA)
        curPosition = interfaces.stageMover.getPosition()
        for repNum in xrange(numReps):
            startTime = time.time()
            curTime = startTime
            
            for i, (eventTime, handler, action) in enumerate(table[startIndex:stopIndex]):
                timeOffset = time.time() - startTime
                if action and handler.deviceType == depot.CAMERA:
                    # Rising edge of a camera trigger: scan until the falling
                    # edge to find what light sources are involved.
                    usedLights = set()
                    for j, (altTime, altHandler, altAction) in enumerate(table[i + 1:stopIndex]):
                        if altHandler in allLights:
                            altHandler.setEnabled(True)
                            usedLights.add(altHandler)
                        if altHandler is handler and not altAction:
                            exposureTime = altTime - eventTime
                            handler.setExposureTime(exposureTime)
                            break
                    interfaces.imager.takeImage(shouldBlock = True)
                    for light in usedLights:
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
