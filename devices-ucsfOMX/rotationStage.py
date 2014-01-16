import device
import events
import handlers.executor
import handlers.genericPositioner
import util.logger

import Pyro4
import threading
import time

CLASS_NAME = 'RotationStageDevice'


## This Device is for interacting with the rotation stage used in SI
# experiments.
class RotationStageDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## IP address for the rotation stage program
        self.ipAddress = '192.168.12.50'
        ## Port for the rotation stage program.
        self.port = 7768
        ## Connection to the rotation stage program
        self.connection = None
        ## Our GenericPositionerHandler instance.
        self.handler = None
        ## Cached position of the rotation stage, in degrees.
        self.curPosition = None
        ## If we should stop waiting for the rotation stage.
        self.shouldAbort = False
        events.subscribe('user abort', self.onAbort)


    def initialize(self):
        self.connect()


    ## (Re)-establish a connection to the rotation stage program.
    def connect(self):
        self.connection = Pyro4.Proxy(
                'PYRO:rotStage@%s:%d' % (self.ipAddress, self.port))


    def getHandlers(self):
        self.handler = handlers.genericPositioner.GenericPositionerHandler(
                "SI angle", "rotation stage", True,
                {'moveAbsolute': self.moveAbsolute,
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition, 
                    'getMovementTime': self.getMovementTime})
        result = [self.handler]
        result.append(handlers.executor.ExecutorHandler(
                "rotation stage executor", "rotation stage",
                {'examineActions': lambda *args: None, 
                    'getNumRunnableLines': self.getNumRunnableLines,
                    'executeTable': self.executeTable}))
        return result


    ## User clicked the abort button.
    def onAbort(self):
        self.shouldAbort = True


    # We sometimes mysteriously lose our connection to the rotation stage
    # program on Nano, hence the retry logic.
    def retry(self, func, message):
        for i in xrange(10):
            if self.shouldAbort:
                return
            try:
                func()
                return
            except Exception, e:
                util.logger.log.error("Failed to %s: %s", message, e)
                self.connect()
        raise RuntimeError("Failed to %s after 10 tries" % message)


    ## Rotate to the specified angle, and wait for the stage to stop.
    # The angle is 0, 1, or 2, which we map to a position in degrees.
    def moveAbsolute(self, name, pos):
        if pos < 0 or pos > 2:
            raise RuntimeError("Invalid rotation stage position %s" % pos)
        target = -15 + pos * 60
        if target == self.curPosition:
            # Already at target position; do nothing.
            return
        events.publish('update status light', 'device waiting',
                'Waiting for\nrotation stage', (255, 255, 0))
        self.shouldAbort = False
        # Always rehome before moving, to ensure that we don't accidentally
        # wrap the rotation stage's wires around.
        self.retry(lambda: self.connection.start(), "rehome the rotation stage")
        self.retry(lambda: self.connection.moveAngle(target),
                "move the rotation stage to %s" % target)
        # Wait in small increments so that the user can abort us.
        self.retry(lambda: self.connection.rotWaitForStop(waitTime = 4000),
                "wait for the rotation stage to stop")
        self.curPosition = target
        events.publish('update status light', 'device waiting',
                '', (170, 170, 170))


    ## Move by the specified delta.
    def moveRelative(self, name, delta):
        raise RuntimeError("The rotation stage doesn't support relative motion.")


    ## Get the current position.
    def getPosition(self, name):
        return self.curPosition


    ## Get the amount of time needed to move from the first position to the 
    # second, and the stabilization time after moving, in milliseconds. This
    # is just an estimate in our case -- experiment execution will be 
    # interrupted until we're done anyway.
    def getMovementTime(self, name, start, end):
        return (20000, 1000)


    ## Determine how many lines we can execute of the provided ActionTable.
    def getNumRunnableLines(self, name, table, index):
        count = 0
        for time, handler, parameter in table[index:]:
            if handler is not self.handler:
                break
            count += 1
        return count


    def executeTable(self, name, table, startIndex, stopIndex, numReps,
            repDuration):
        for rep in xrange(numReps):
            for actionTime, handler, parameter in table[startIndex:stopIndex]:
                if handler is not self.handler:
                    raise RuntimeError("Tried to do a non-rotation action (%s) with the RotationStageDevice" % handler.name)
                self.moveAbsolute(handler.name, parameter)
        events.publish('experiment execution')

