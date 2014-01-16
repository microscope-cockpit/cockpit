import depot
import device
import events
import handlers.executor

import time

CLASS_NAME = 'ExperimentExecutorDevice'



class ExperimentExecutorDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)

    
    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.ExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable})]


    ## Given an experiment.ActionTable instance, examine the actions and 
    # make any necessary modifications.
    def examineActions(self, name, table):
        pass


    ## Figure out how many lines of the provided table we can execute on our
    # own, starting from the specified index. In our case, we can execute 
    # everything in the dummy device set.
    def getNumRunnableLines(self, name, table, curIndex):
        return len(table) - curIndex


    ## Execute the table of experiment actions.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        for i in xrange(numReps):
            startTime = time.time()
            curTime = startTime
            for eventTime, handler, action in table[startIndex:stopIndex]:
                if action and handler.deviceType == depot.CAMERA:
                    # Rising edge of a camera trigger: take an image.
                    events.publish("dummy take image", handler)
                eventTime = float(eventTime)
                targetTime = startTime + (eventTime / 1000)
                time.sleep(max(0, targetTime - curTime))
                curTime = time.time()
            if repDuration is not None:
                # Wait out the remaining rep time.
                # Convert repDuration from milliseconds to seconds.
                waitTime = (repDuration / 1000) - (time.time() - startTime)
                time.sleep(max(0, waitTime))
        events.publish("experiment execution")
