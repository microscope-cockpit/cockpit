import depot
import device
import events
import handlers.executor

import time

CLASS_NAME = 'ExperimentExecutorDevice'

class DummyExecutor(device.Device):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        self.deviceType = 'experiment executor'

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.ExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
                'executeTable': self.executeTable,})]

    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, name, table):
        pass

    ## Execute the table of experiment actions.
    def executeTable(self, name, table, startIndex, stopIndex, numReps,
            repDuration):
        # time this executor starts
        tStart = time.time()
        if startIndex > 0:
            tStart -= float(table[startIndex-1][0] / 1000)
        for i in xrange(numReps):
            for tTable, handler, action in table[startIndex:stopIndex]:
                tNext = float(tTable/1000) + tStart
                time.sleep(max(0, tNext - time.time()))
                if action and handler.deviceType == depot.CAMERA:
                    # Rising edge of a camera trigger: take an image.
                    events.publish("dummy take image", handler)
            if repDuration is not None:
                # Wait out the remaining rep time.
                # Convert repDuration from milliseconds to seconds.
                tWait = (repDuration / 1000) - (time.time() - tStart)
                time.sleep(max(0, tWait))
        events.publish("experiment execution")


class DummyDigitalExecutor(DummyExecutor):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        self.deviceType = 'experiment executor'

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.DigitalExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
                'executeTable': self.executeTable,
             'setDigital': self.setDigital})]

    def setDigital(self, line, state):
        print("Set line %s %s." % (line, ['low', 'high'][state]))

    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, name, table):
        pass


class DummyAnalogDigitalExecutor(DummyExecutor):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        self.deviceType = 'experiment executor'

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [handlers.executor.AnalogDigitalExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
                'executeTable': self.executeTable,
             'setDigital': self.setDigital,
            'setAnalog': self.setAnalog}),]

    def setDigital(self, line, state):
        print("Set d-line %s %s." % (line, ['low', 'high'][state]))

    def setAnalog(self, line, level):
        print("Set a-line %s %s." % (line, level))

    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, name, table):
        pass

