## This module creates a simple stage-positioning device.

import depot
import device
import events
import handlers.stagePositioner

CLASS_NAME = 'DummyZStage'

class DummyZStage(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.curPosition = 100
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')
        self.deviceType = "stage positioner"
        self.axes = [2]


    def initialize(self):
        # At this point we would normally get the true stage position from
        # the actual device, but of course we have no such device.
        events.subscribe('user abort', self.onAbort)
        pass
        

    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        axis = 2
        minVal = 0
        maxVal = 25000
        handler = handlers.stagePositioner.PositionerHandler(
            "%d dummy mover" % axis, "%d stage motion" % axis, True, 
            {'moveAbsolute': self.moveAbsolute,
                'moveRelative': self.moveRelative, 
                'getPosition': self.getPosition, 
                'getMovementTime': self.getMovementTime,
                'cleanupAfterExperiment': self.cleanup,
                'setSafety': self.setSafety},
                axis, [.01, .05, .1, .5, 1, 5, 10, 50, 100, 500, 1000, 5000],
                2, (minVal, maxVal), (minVal, maxVal))
        result.append(handler)
        return result


    ## Publish our current position.
    def makeInitialPublications(self):
        axis = 2
        events.publish('stage mover', '%d dummy mover' % axis, axis,
                self.curPosition)


    ## User clicked the abort button; stop moving.
    def onAbort(self):
        axis = 2
        events.publish('stage stopped', '%d dummy mover' % axis)


    ## Move the stage piezo to a given position.
    def moveAbsolute(self, axis, pos):
        self.curPosition = pos
        # Dummy movers finish movement immediately.
        events.publish('stage mover', '%d dummy mover' % axis, axis, 
                self.curPosition)
        events.publish('stage stopped', '%d dummy mover' % axis)


    ## Move the stage piezo by a given delta.
    def moveRelative(self, axis, delta):
        self.curPosition += delta
        # Dummy movers finish movement immediately.
        events.publish('stage mover', '%d dummy mover' % axis, axis, 
                self.curPosition)
        events.publish('stage stopped', '%d dummy mover' % axis)


    ## Get the current piezo position.
    def getPosition(self, axis):
        return self.curPosition


    ## Get the amount of time it would take the mover to move from the 
    # initial position to the final position, as well
    # as the amount of time needed to stabilize after that point, 
    # both in milliseconds. This is needed when setting up timings for 
    # experiments.
    def getMovementTime(self, axis, start, end):
        return (1, 1)


    ## Set the soft motion safeties for one of the movers. Note that the 
    # PositionerHandler provides its own soft safeties on the cockpit side; 
    # this function just allows you to propagate safeties to device control
    # code, if applicable.
    def setSafety(self, axis, value, isMax):
        pass


    ## Cleanup after an experiment. For a real mover, this would probably 
    # just mean making sure we were back where we were before the experiment
    # started.
    def cleanup(self, axis, isCleanupFinal):
        pass
