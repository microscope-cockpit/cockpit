import device
import events
import gui.guiUtils
import handlers.stagePositioner
import interfaces
import util.logger
import util.threads
import util.userConfig

from OpenGL.GL import *
import Pyro4
import serial
import socket
import threading
import time

## This module is for Physik Instrumente (PI) stage motion
# devices. It controls the XY stage, and sets up but does not directly
# control the Z piezo -- that is handled by the analog voltage signal from
# the DSP device.


# Z piezo notes:
# The degree of motion of the piezo for a given voltage input is controlled
# via offset and gain, parameters are 0x02000200 and 0x02000300 respectively.
# Use SPA to set volatile memory and WPA to write volatile memory to nonvolatile
# (so settings will be remembered on reboot). E.g. for offset 0 and gain 2,
# do
# % SPA 2 0x02000200 0
# % SPA 2 0x02000300 2
# (The first 2 refers to the input channel, which in this case is the analog
# input line from the DSP).
 

CLASS_NAME = 'PhysikInstrumenteDevice'

## Maps error codes to short descriptions. These appear to be the
# same for the Z piezo controller and the XY stage system, so we re-use them.
# Massively incomplete; just some common codes here. Check the manual
# for more information (errors codes start on page 195 of
# E-753_User_PZ193E100.pdf or page 202 of C-867_262_User_MS196E100.pdf).
ERROR_CODES = {
    1: 'Syntax error',
    2: 'Unknown command',
    3: 'Command too long',
    4: 'Error while scanning',
    5: "Can't move because servo is off or axis has no reference. Most likely the axis needs to be rehomed; remove the objective from its mount (or otherwise ensure no collision is possible with the sample holder, e.g. raise the Picomotors) and then do sendXYCommand('FRF'). Please know what you are doing before you try this.",
    7: 'Position out of limits',
    8: 'Velocity out of limits',
    10: 'Controller was stopped by command',
    15: 'Invalid axis',
    17: 'Parameter out of range',
    23: 'Invalid axis',
    24: 'Incorrect number of parameters',
    25: 'Invalid floating-point number',
    26: 'Missing parameter',
    -1024: 'Position error too large; servo automatically switched off',
}

## These two pairs of vertices define two rectangles that the stage is not 
# allowed to pass through, as doing so would cause the objective to collide
# with part of the sample holder. 
# Compare stage motion limits X: (-24500, 25000), Y: (-43000, 42500).
BANNED_RECTANGLES = (
        ((25000, -12500), (17500, -43000)),
        ((-12500, -18000), (-24500, -43000))
)


class PhysikInstrumenteDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Connection to the Z piezo controller (Pyro4.Proxy of a
        # telnetlib.Telnet instance)
        self.zConnection = None
        ## Lock around sending commands to the Z piezo controller.
        self.zLock = threading.Lock()
        ## Connection to the XY stage controller (serial.Serial instance)
        self.xyConnection = None
        ## Lock around sending commands to the XY stage controller.
        self.xyLock = threading.Lock()
        ## Cached copy of the stage's position. Initialized to an impossible
        # value; this will be modified in initialize.
        self.xyPositionCache = (10 ** 100, 10 ** 100)
        ## Target positions for movement in X and Y, or None if that axis is 
        # not moving.
        self.xyMotionTargets = [None, None]
        ## Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering (1: Y, 2: X)
        self.axisMapper = {0: 2, 1: 1}
        ## Maps cockpit axis ordering to a +-1 multiplier to apply to motion,
        # since some of our axes are flipped.
        self.axisSignMapper = {0: -1, 1: 1}
        ## Time of last action using the piezo; used for tracking if we should
        # disable closed loop.
        self.lastPiezoTime = time.time()

        events.subscribe('user logout', self.onLogout)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('macro stage xy draw', self.onMacroStagePaint)
        events.subscribe('cockpit initialization complete',
                self.promptExerciseStage)


    def initialize(self):
        # Note we assume that the Z proxy is on the same host as the cockpit.
        self.zConnection = Pyro4.Proxy('PYRO:PIZProxy@%s:%d' %
                (socket.gethostbyname(socket.gethostname()), 7790))
        # Enable closed-loop positioning for the Z piezo.
        self.sendZCommand('SVO 1 1')
        # Enable advanced commands.
        self.sendZCommand('CCL 1 advanced')
        # Switch to analog voltage control (via the DSP). NB setting
        # 0 here would change it back to being controlled only via software.
        self.sendZCommand('SPA 1 0x06000500 2')

        self.xyConnection = serial.Serial('COM3', 115200, timeout = .05)
        self.sendXYCommand('SVO 1 1')
        self.sendXYCommand('SVO 2 1')
        # Get the proper initial position.
        self.getXYPosition(shouldUseCache = False)
        events.oneShotSubscribe('cockpit initialization complete',
                self.timedDisableClosedLoop)


    ## We want to periodically exercise the XY stage to spread the grease
    # around on its bearings; check how long it's been since the stage was
    # last exercised, and prompt the user if it's been more than a week.
    def promptExerciseStage(self):
        lastExerciseTimestamp = util.userConfig.getValue(
                'PILastExerciseTimestamp',
                isGlobal = True, default = 0)
        curTime = time.time()
        delay = curTime - lastExerciseTimestamp
        daysPassed = delay / float(24 * 60 * 60)
        if (daysPassed > 7 and
                gui.guiUtils.getUserPermission(
                    ("It has been %.1f days since " % daysPassed) +
                    "the stage was last exercised. Please exercise " +
                    "the stage regularly.\n\nExercise stage?",
                    "Please exercise the stage")):
            # Move to the middle of the stage, then to one corner, then to
            # the opposite corner, repeat a few times, then back to the middle,
            # then to where we started from. Positions are actually backed off
            # a fair bit from the true safeties. Moving to the middle is
            # necessary to avoid the banned rectangles, in case the stage is
            # in them when we start.
            initialPos = tuple(self.xyPositionCache)
            interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            for i in xrange(5):
                print "Rep %d of 5..." % i
                for position in [(20000, -10000), (-20000, 40000)]:
                    interfaces.stageMover.goToXY(position, shouldBlock = True)
            interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            interfaces.stageMover.goToXY(initialPos, shouldBlock = True)
            print "Exercising complete. Thank you!"
            
            util.userConfig.setValue('PILastExerciseTimestamp',
                    time.time(), isGlobal = True)


    ## This function disables closed loop on the Z piezo if the scope has been
    # idle for some time.
    @util.threads.callInNewThread
    def timedDisableClosedLoop(self):
        amInClosedLoop = True
        # Disable this loop (and ensure that closed-loop positioning is on)
        # when an experiment is in progress.
        def disableDuringExperiment(*args):
            self.sendZCommand('SVO 1 1')
            amInClosedLoop = True
            self.lastPiezoTime = None
        events.subscribe('prepare for experiment', disableDuringExperiment)
        
        # Re-enable when experiments end.
        def enableAfterExperiment(*args):
            self.lastPiezoTime = time.time()
        events.subscribe('experiment complete', enableAfterExperiment)

        # End the loop on program exit.
        amDone = False
        def finish(*args):
            amDone = True
        events.subscribe('program exit', finish)

        try:
            curZPos = lastZPos = interfaces.stageMover.getPositionForAxis(2)
            while not amDone:
                curZPos = interfaces.stageMover.getPositionForAxis(2)
                if (self.lastPiezoTime is not None and amInClosedLoop and 
                        time.time() - self.lastPiezoTime > 3600):
                    # It's been at least an hour since any actions with the piezo
                    # were taken; assume the scope is sitting idle and
                    # disable closed loop.
                    # Remember lastPiezoTime as sendZCommand resets it.
                    trueLastTime = self.lastPiezoTime
                    self.sendZCommand('SVO 1 0')
                    self.lastPiezoTime = trueLastTime
                    amInClosedLoop = False
                elif not amInClosedLoop and curZPos != lastZPos:
                    # We've disabled closed loop in the past, but the user
                    # has taken actions; re-enable closed loop.
                    self.sendZCommand('SVO 1 1')
                    amInClosedLoop = True
                lastZPos = curZPos
                time.sleep(1)
            # Program exiting; redundantly disable closed loop.
            self.sendZCommand('SVO 1 0')
        except Exception, e:
            util.logger.log.error("Closed-loop disabler thread failed: %s" % e)
            import traceback
            util.logger.log.error(traceback.format_exc())
        

    ## Send a command to the Z piezo controller, read the response, check
    # for errors, and either raise an exception or return the response.
    def sendZCommand(self, command):
        with self.zLock:
            self.lastPiezoTime = time.time()
            self.zConnection.write(command + '\n')
            response = self.zConnection.read_until('\n', .25)
            while True:
                # Read out any additional lines
                line = self.zConnection.read_until('\n', .05)
                if not line:
                    break
                response += line
            # Check for errors
            self.zConnection.write('ERR?\n')
            error = int(self.zConnection.read_until('\n', .5).strip())
            if error != 0: # 0 is "no error"
                errorDesc = ERROR_CODES.get(error,
                        'Unknown error code [%s]' % error)
                raise RuntimeError("Error issuing command [%s] to the Z piezo controller: %s" % (command, errorDesc))
            return response


    ## Send a command to the XY stage controller, read the response, check
    # for errors, and either raise an exception or return the response.
    # Very similar to sendZCommand of course, but xyConnection is a Serial
    # instance and zConnection is a Telnet instance.
    # We prevent commands from being sent if too much time passes before we
    # can acquire the lock, since otherwise we may buffer up a lot of
    # user-input motion commands and end up moving further than expected.
    def sendXYCommand(self, command, numExpectedLines = 1, shouldCheckErrors = True):
        with self.xyLock:
            self.xyConnection.write(command + '\n')
            response = self.getXYResponse(numExpectedLines)
            if shouldCheckErrors:
                # Check for errors
                self.xyConnection.write('ERR?\n')
                error = int(self.getXYResponse(1).strip())
                # 0 is "no error"; 10 is "motion stopped by user".
                if error not in [0, 10]:
                    errorDesc = ERROR_CODES.get(error,
                            'Unknown error code [%s]' % error)
                    raise RuntimeError("Error issuing command [%s] to the XY stage controller: %s" % (command, errorDesc))
            return response


    ## Read a response off of the XY connection. We do this one character
    # at a time in the hopes of avoiding having to wait for a timeout. We
    # stop when we hit the right number of newlines.
    def getXYResponse(self, numExpectedLines):
        response = ''
        numLines = 0
        while True:
            output = self.xyConnection.read(1)
            if output:
                response += output
                if output == '\n':
                    numLines += 1
                    if numLines == numExpectedLines:
                        break
            else:
                # No output; must be done.
                break
        return response


    ## When the user logs out, switch to open-loop mode.
    def onLogout(self, *args):
        # Switch to open loop
        self.sendZCommand('SVO 1 0')
        self.sendXYCommand('SVO 1 0')
        self.sendXYCommand('SVO 2 0')
        self.xyConnection.close()


    ## Halt XY motion when the user aborts. Note we can't control Z motion
    # here because the piezo is under the DSP's control.
    def onAbort(self, *args):
        self.sendXYCommand('HLT')


    ## The XY Macro Stage view is painting itself; draw the banned
    # rectangles as pink excluded zones.
    def onMacroStagePaint(self, stage):
        glColor3f(1, .6, .6)
        glBegin(GL_QUADS)
        for (x1, y1), (x2, y2) in BANNED_RECTANGLES:
            stage.scaledVertex(x1, y1)
            stage.scaledVertex(x1, y2)
            stage.scaledVertex(x2, y2)
            stage.scaledVertex(x2, y1)
        glEnd()


    def getHandlers(self):
        # Note we leave control of the Z axis to the DSP; only the XY
        # stage movers get handlers here.
        result = []
        # NB these motion limits are more restrictive than the stage's true
        # range of motion, but they are needed to keep the stage from colliding
        # with the objective. 
        # True range of motion is (-67500, 67500) for X, (-42500, 42500) for Y.
        for axis, minPos, maxPos in [(0, -24500, 25000),
                    (1, -43000, 42500)]:
            result.append(handlers.stagePositioner.PositionerHandler(
                    "%d PI mover" % axis, "%d stage motion" % axis, False,
                    {'moveAbsolute': self.moveXYAbsolute,
                         'moveRelative': self.moveXYRelative,
                         'getPosition': self.getXYPosition,
                         'setSafety': self.setXYSafety},
                    axis, [.1, .2, .5, 1, 2, 5, 10, 50, 100, 500, 1000, 5000], 3,
                    (minPos, maxPos), (minPos, maxPos)))
        return result


    def moveXYAbsolute(self, axis, pos):
        with self.xyLock:
            if self.xyMotionTargets[axis] is not None:
                # Don't stack motion commands for the same axis
                return
        self.xyMotionTargets[axis] = pos
        if not self.isMotionSafe(axis):
            self.xyMotionTargets[axis] = None
            raise RuntimeError("Moving axis %d to %s would pass through unsafe zone" % (axis, pos))
        # The factor of 1000 converts from microns to millimeters.
        self.sendXYCommand('MOV %d %f' %
                (self.axisMapper[axis],
                 self.axisSignMapper[axis] * pos / 1000.0))
        self.sendXYPositionUpdates()


    def moveXYRelative(self, axis, delta):
        if not delta:
            # Received a bogus motion request.
            return
        curPos = self.xyPositionCache[axis]
        self.moveXYAbsolute(axis, curPos + delta)


    # Verify that the desired motion is safe, i.e. doesn't take us through
    # either of the banned rectangles. We define a rectangle that consists
    # of all of the potential locations that the stage could occupy between
    # its current position and its target position, and test for overlap
    # between that rectangle and the banned rectangles.
    def isMotionSafe(self, axis):
        # Make copies of these values for safety's sake (so they don't get
        # unexpectedly altered).
        start = tuple(self.xyPositionCache)
        end = list(self.xyMotionTargets)
        for i, val in enumerate(end):
            if val is None:
                # Not moving this axis; hold it fixed.
                end[i] = start[i]
        end = tuple(end)
        for rectangle in BANNED_RECTANGLES:
            if self.doBoxesIntersect(start, end, rectangle):
                return False
        return True


    ## Test if the given two axis-aligned rectangles overlap. We do this by
    # looking to see if either of their axial projections *don't* overlap
    # (a simple application of the Separating Axis theorem). 
    def doBoxesIntersect(self, start, end, rectangle):
        for axis in xrange(2):
            # a = minimum value for axis; b = maximum value; 1 = first 
            # rectangle, 2 = second rectangle.
            a1 = start[axis]
            b1 = end[axis]
            if b1 < a1:
                a1, b1 = b1, a1
            a2 = rectangle[0][axis]
            b2 = rectangle[1][axis]
            if b2 < a2:
                a2, b2 = b2, a2
            # We can short-circuit if we verify that there is no overlap.
            # The test is if the maximum value of 1 is less than the minimum
            # value of 2, or vice versa.
            if (b1 < a2 or a1 > b2):
                return False
        return True


    ## Send updates on the XY stage's position, until it stops moving.
    @util.threads.callInNewThread
    def sendXYPositionUpdates(self):
        while True:
            prevX, prevY = self.xyPositionCache
            x, y = self.getXYPosition(shouldUseCache = False)
            delta = abs(x - prevX) + abs(y - prevY)
            if delta < .1:
                # No movement since last time; done moving.
                for axis in [0, 1]:
                    events.publish('stage stopped', '%d PI mover' % axis)
                with self.xyLock:
                    self.xyMotionTargets = [None, None]
                return
            for axis, val in enumerate([x, y]):
                events.publish('stage mover', '%d PI mover' % axis, axis,
                        self.axisSignMapper[axis] * val)
            curPosition = (x, y)
            time.sleep(.1)


    ## Get the position of the specified axis, or both axes by default.
    # If shouldUseCache is not set, then we will query the controller, which
    # takes some time.
    def getXYPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            position = self.sendXYCommand('POS?', 2, False)
            y, x, null = position.split('\n')
            # Positions are in millimeters, and we need microns.
            x = float(x.split('=')[1]) * 1000 * self.axisSignMapper[0]
            y = float(y.split('=')[1]) * 1000 * self.axisSignMapper[1]
            self.xyPositionCache = (x, y)
        if axis is None:
            return self.xyPositionCache
        return self.xyPositionCache[axis]


    def setXYSafety(self, axis, value, isMax):
        pass


    def makeInitialPublications(self):
        self.sendXYPositionUpdates()


    ## Debugging function: extract all valid parameters from the XY controller.
    def listXYParams(self):
        # Don't use sendXYCommand here because its error handling doesn't
        # deal with HPA?'s output properly -- there's an extra blank line
        # that makes it think output is done when it actually isn't.
        self.xyConnection.write('HPA?\n')
        lines = ''
        output = None
        
        while output or len(lines) < 1000:
            output = self.xyConnection.read(100)
            lines += output
        lines = lines.split('\n')
        handle = open('params.txt', 'w')
        for line in lines:
            if '0x' in line:
                # Parameter line
                param = line.split('=')[0]
                desc = line.split('\t')[5]
                for axis in (1, 2):
                    val = self.sendXYCommand('SPA? %d %s' % (axis, param))
                    # Note val has a newline at the end here.
                    handle.write("%s (%s): %s" % (desc, param, val))
            else:
                # Lines at the beginning/end don't have parameters in them.
                handle.write(line)
        handle.write('\n\n')
        handle.close()


    ## Debugging function: extract all valid parameters from the Z controller.
    def listZParams(self):
        # Don't use sendZCommand here because its error handling doesn't
        # deal with HPA?'s output properly -- there's an extra blank line
        # that makes it think output is done when it actually isn't.
        self.zConnection.write('HPA?\n')
        time.sleep(1)
        lines = self.zConnection.read_very_eager()
        
        lines = lines.split('\n')
        handle = open('zparams.txt', 'w')
        for line in lines:
            if '0x' in line:
                # Parameter line
                param = line.split('=')[0]
                desc = line.split('\t')[5]
                val = self.sendZCommand('SPA? 1 %s' % param)
                # Note val has a newline at the end here.
                handle.write("%s (%s): %s" % (desc, param, val))
            else:
                # Lines at the beginning/end don't have parameters in them.
                handle.write(line)
        handle.write('\n\n')
        handle.close()


    ## Debugging function: test doBoxesIntersect().
    def testBoxIntersect(self):
        for items in [
                [(0, 0), (10, 10), ((5, 5), (15, 15)), True],
                [(5, 5), (15, 5), ((0, 0), (10, 10)), True],
                [(5, 5), (5, 15), ((0, 0), (10, 10)), True],
                [(0, 0), (2, 2), ((6, 6), (8, 8)), False]]:
            print items
            start, end, (boxStart, boxEnd), desire = items
            assert(self.doBoxesIntersect(start, end, (boxStart, boxEnd)) == desire)
            s1, s2 = start
            e1, e2 = end
            bs1, bs2 = boxStart
            be1, be2 = boxEnd
            assert(self.doBoxesIntersect((s2, s1), (e2, e1), ((bs2, bs1), (be2, be1))) == desire)
            assert(self.doBoxesIntersect((-s1, s2), (-e1, e2), ((-bs1, bs2), (-be1, be2))) == desire)
            assert(self.doBoxesIntersect((-s1, -s2), (-e1, -e2), ((-bs1, -bs2), (-be1, -be2))) == desire)
            assert(self.doBoxesIntersect((s1, -s2), (e1, -e2), ((bs1, -bs2), (be1, -be2))) == desire)


