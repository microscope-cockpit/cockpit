import device
import events
import handlers.stagePositioner
import util.threads

import numpy
import Pyro4
import re
import socket
import threading

CLASS_NAME = 'PicomotorDevice'


class PicomotorDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = False
        ## Connection to the controller (Pyro4 proxy of a Telnet instance)
        self.connection = None
        ## Lock on communicating with the controller.
        self.lock = threading.Lock()
        ## Cached copy of the device positions -- a list of floats.
        self.curPosition = [0, 0, 0]


    def initialize(self):
        self.connection = Pyro4.Proxy('PYRO:PicomotorProxy@%s:%d' %
                (socket.gethostbyname(socket.gethostname()), 7791))
#        self.getPosition(shouldUseCache = False)


    def getHandlers(self):
        return []
        # 2 for the Z axis, the only one we control.
        return [handlers.stagePositioner.PositionerHandler(
                '2 Picomotor', '2 stage motion', False,
                {'moveAbsolute': self.moveAbsolute,
                     'moveRelative': self.moveRelative,
                     'getPosition': self.getPosition,
                     'setSafety': self.setSafety},
                2, [.1, .5, 1, 10, 100, 1000, 5000], 3,
                (0, 10000), (0, 10000))]


    def makeInitialPublications(self):
        self.sendPositionUpdates()


    def sendCommand(self, command):
        with self.lock:
            self.connection.write(command + '\n')
            response = self.connection.read_until('\n', .25)
            while True:
                # Read out any additional lines
                line = self.connection.read_until('\n', .05)
                if not line:
                    break
                response += line
            return response


    ## Move all three devices to the specified position.
    def moveAbsolute(self, axis, position):
        print self.sendCommand('abs a1=%d g' % position)
        print self.sendCommand('abs a2=%d g' % position)
        print self.sendCommand('abs a3=%d g' % position)
        self.sendPositionUpdates()
        

    ## Move all three devices by the specified offset.
    def moveRelative(self, axis, delta):
        self.sendCommand('rel a1=%d g' % delta)
        self.sendCommand('rel a2=%d g' % delta)
        self.sendCommand('rel a3=%d g' % delta)
        self.sendPositionUpdates()


    ## Publish the new position of the mover at regular intervals, until it
    # stops moving.
    @util.threads.callInNewThread
    def sendPositionUpdates(self):
        pass
        

    ## Return the current position of the devices, in microns. Since we're
    # representing three combined devices as a single device, we just use their
    # average position.
    def getPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            positions = [self.sendCommand('pos a%d' % i) for i in xrange(1, 4)]
            for i, line in enumerate(positions):
                # Extract the number following the equals sign.
                val = float(re.search(r'=(\d+\.?\d*)', line).group(1))
                self.curPosition[i] = val
        print self.curPosition
        return numpy.mean(self.curPosition)


    ## Set safeties. Currently a no-op.
    def setSafety(self, axis, pos, isMax):
        pass


    ## Test function: move the axes back and forth.
    def testMotion(self, numReps, distance):
        import time
        handle = open('motionTest.txt', 'w')
        for i in xrange(numReps):
            responses = []
            for axis in xrange(1, 4):
                responses.append(self.sendCommand('rel a%d=%d g' % (axis, distance)))
            handle.write("Forward motion responses: %s\n" % responses)
            handle.write("Status: %s\n" % self.sendCommand('sta'))
            curPos = self.getPosition(shouldUseCache = False)
            while True:
                time.sleep(1)
                newPos = self.getPosition(shouldUseCache = False)
                if abs(newPos - curPos) < 10:
                    break
                curPos = newPos
            responses = []
            for axis in xrange(1, 4):
                responses.append(self.sendCommand('rel a%d=%d g' % (axis, -distance)))
            handle.write( "Reverse motion responses: %s\n" % responses)
            curPos = self.getPosition(shouldUseCache = False)
            while True:
                time.sleep(1)
                newPos = self.getPosition(shouldUseCache = False)
                if abs(newPos - curPos) < 10:
                    break
                curPos = newPos
            handle.write("Status: %s\n" % self.sendCommand('sta'))
        handle.close()
