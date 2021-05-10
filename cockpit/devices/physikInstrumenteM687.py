#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.

from cockpit import events
import cockpit.gui.guiUtils
import cockpit.handlers.stagePositioner
import cockpit.interfaces.stageMover
import cockpit.util.logger
import cockpit.util.threads
import cockpit.util.userConfig

from cockpit.devices.device import Device
from OpenGL.GL import *
import serial
import threading
import time
import wx
import re # to get regular expression parsing for config file

LIMITS_PAT = r"(?P<limits>\(\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*\,\s*[-]?\d*\s*\)\))"

## TODO:  Test with hardware.
## TODO:  These parameters should be factored out to a config file.

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
BANNED_RECTANGLES = ()
# IMD 2015-03-02 removed as not relevant for DeepSIM
#  ((25000, -12500), (17500, -43000)),
#        ((-12500, -18000), (-24500, -43000))
#)


class PhysikInstrumenteM687(Device):
    """Physik Instrumente (PI) M687 XY stage.

    Sample config entry:

    .. code:: ini

        [m687]
        type: cockpit.devices.physikInstrumenteM687.PhysikInstrumenteM687
        port: com6
        baud: 115200
        timeout: 0.1
        softlimits: ((-37500,-67500),(11500,59500))

    """

    _config_types = {'baud': int,
                     'timeout': float,}
    def __init__(self, name, config):
        super().__init__(name, config)
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

        ## If there is a config section for the m687, grab the config and
        # subscribe to events.
        self.port = config.get('port')
        self.baud = config.get('baud')
        self.timeout = config.get('timeout')
        try :
            limitString = config.get('softlimits')
            parsed = re.search(LIMITS_PAT, limitString)
            if not parsed:
                # Could not parse config entry.
                raise Exception('Bad config: PhysikInstrumentsM687 Limits.')
                # No transform tuple
            else:
                lstr = parsed.groupdict()['limits']
                self.softlimits=eval(lstr)
        except:
            print ("No softlimits section setting default limits")
            self.softlimits = ((-67500, 67500), (-42500, 42500))

        events.subscribe(events.USER_ABORT, self.onAbort)
        events.subscribe('macro stage xy draw', self.onMacroStagePaint)
        #events.subscribe('cockpit initialization complete', self.promptExerciseStage)


    def initialize(self):
        port = self.port
        baud = self.baud
        timeout = self.timeout
        self.xyConnection = serial.Serial(port, baud, timeout=timeout)
        self.sendXYCommand(b'SVO 1 1')
        self.sendXYCommand(b'SVO 2 1')
        # Get the proper initial position.
        self.getXYPosition(shouldUseCache = False)

    ## We want to periodically exercise the XY stage to spread the grease
    # around on its bearings; check how long it's been since the stage was
    # last exercised, and prompt the user if it's been more than a week.
    def promptExerciseStage(self):
        lastExerciseTimestamp = cockpit.util.userConfig.getValue(
                'PIM687LastExerciseTimestamp', default = 0)
        curTime = time.time()
        delay = curTime - lastExerciseTimestamp
        daysPassed = delay / float(24 * 60 * 60)
        if (daysPassed > 7 and
                cockpit.gui.guiUtils.getUserPermission(
                    ("It has been %.1f days since " % daysPassed) +
                    "the stage was last exercised. Please exercise " +
                    "the stage regularly.\n\nExercise stage?",
                    "Please exercise the stage")):
            # Move to the middle of the stage, then to one corner, then to
            # the opposite corner, repeat a few times, then back to the middle,
            # then to where we started from. Positions are actually backed off
            # slightly from the true safeties. Moving to the middle is
            # necessary to avoid the banned rectangles, in case the stage is
            # in them when we start.
            initialPos = tuple(self.xyPositionCache)
            cockpit.interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            for i in range(5):
                print ("Rep %d of 5..." % i)
                for position in self.softlimits:
                    cockpit.interfaces.stageMover.goToXY(position, shouldBlock = True)
            cockpit.interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            cockpit.interfaces.stageMover.goToXY(initialPos, shouldBlock = True)
            print ("Exercising complete. Thank you!")

            cockpit.util.userConfig.setValue('PIM687LastExerciseTimestamp',
                                             time.time())


    ## Send a command to the XY stage controller, read the response, check
    # for errors, and either raise an exception or return the response.
    # Very similar to sendZCommand of course, but xyConnection is a Serial
    # instance and zConnection is a Telnet instance.
    # We prevent commands from being sent if too much time passes before we
    # can acquire the lock, since otherwise we may buffer up a lot of
    # user-input motion commands and end up moving further than expected.
    def sendXYCommand(self, command, numExpectedLines = 1, shouldCheckErrors = True):
        with self.xyLock:
            self.xyConnection.write(command + b'\n')
            response = self.getXYResponse(numExpectedLines)
            if shouldCheckErrors:
                # Check for errors
                self.xyConnection.write(b'ERR?\n')
                error = int(self.getXYResponse(1).strip())
                #0 is "no error"; 10 is "motion stopped by user".
                if error == 5:
                    # Motors need homing.
                    msg = """
                    The XY stage needs to find the home position.
                    Homing the stage will move it to its centre position.
                    Ensure that there are no obstructions, then press 'OK' 
                    to home the stage.
                    """
                    if cockpit.gui.guiUtils.getUserPermission(msg):
                        self.homeMotors()
                elif error not in [0, 10]:
                    errorDesc = ERROR_CODES.get(error,
                            'Unknown error code [%s]' % error)
                    raise RuntimeError("Error issuing command [%s] to the XY stage controller: %s"
                                       % (command.decode(), errorDesc))
            return response


    ## Read a response off of the XY connection. We do this one character
    # at a time in the hopes of avoiding having to wait for a timeout. We
    # stop when we hit the right number of newlines.
    def getXYResponse(self, numExpectedLines):
        response = b''
        numLines = 0
        while True:
            output = self.xyConnection.read(1)
            if output:
                response += output
                if output == b'\n':
                    numLines += 1
                    if numLines == numExpectedLines:
                        break
            else:
                # No output; must be done.
                break
        return response


    ## Home the motors.
    def homeMotors(self):
        # Clear output buffers
        self.xyConnection.readlines()
        self.xyConnection.write(b'SVO 1 1\n')
        self.xyConnection.write(b'SVO 2 1\n')
        self.xyConnection.write(b'FRF\n')
        # Motion status response.
        response = None

        # Progress indicator.
        # TODO - rather than raw wx, this should probably be a class from
        # cockpit.gui.guiUtils.
        busy_box = wx.ProgressDialog(parent = None,
                                     title = 'Busy...', 
                                     message = 'Homing stage')
        busy_box.Show()
        while response != 0:
            # Request motion status
            self.xyConnection.write(b'\x05')
            response = int(self.xyConnection.readline())
            busy_box.Pulse()
            time.sleep(0.2)

        busy_box.Hide()
        busy_box.Destroy()
		
        # Was homing successful?
        self.xyConnection.write(b'FRF?\n')
        homestatus = self.xyConnection.readlines()
        success = True
		
        msg = ''
        for status in homestatus:
            motor, state = status.strip().split(b'=')
            if state != b'1':
                msg += 'There was a problem homing motor %s.\n' % motor.decode()
                success = False
        
        if not success:
            cockpit.gui.guiUtils.showHelpDialog(None, msg)
        else:
            self.sendXYPositionUpdates()
            cockpit.gui.guiUtils.showHelpDialog(None, 'Homing successful.')
            

        return success


    ## When the user logs out, switch to open-loop mode.
    def onExit(self):
        # Switch to open loop
        self.sendXYCommand(b'SVO 1 0')
        self.sendXYCommand(b'SVO 2 0')
        self.xyConnection.close()


    ## Halt XY motion when the user aborts. Note we can't control Z motion
    # here because the piezo is under the DSP's control.
    def onAbort(self, *args):
        self.sendXYCommand(b'HLT')


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
        #IMD 2015-03-02 hacked in full range to see if we can access the full range
        for axis, minPos, maxPos in [(0, self.softlimits[0][0],self.softlimits[1][0]),
                    (1, self.softlimits[0][1],self.softlimits[1][1])]:
            result.append(cockpit.handlers.stagePositioner.PositionerHandler(
                    "%d PI mover" % axis, "%d stage motion" % axis, False,
                    {'moveAbsolute': self.moveXYAbsolute,
                         'moveRelative': self.moveXYRelative,
                         'getPosition': self.getXYPosition},
                    axis, (minPos, maxPos), (minPos, maxPos)))
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
        self.sendXYCommand(b'MOV %d %f' %
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
        for axis in range(2):
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
    @cockpit.util.threads.callInNewThread
    def sendXYPositionUpdates(self):
        while True:
            prevX, prevY = self.xyPositionCache
            x, y = self.getXYPosition(shouldUseCache = False)
            delta = abs(x - prevX) + abs(y - prevY)
            if delta < 5.:
                # No movement since last time; done moving.
                for axis in [0, 1]:
                    events.publish(events.STAGE_STOPPED, '%d PI mover' % axis)
                with self.xyLock:
                    self.xyMotionTargets = [None, None]
                return
            for axis in [0, 1]:
                events.publish(events.STAGE_MOVER, axis)
            time.sleep(.01)


    ## Get the position of the specified axis, or both axes by default.
    # If shouldUseCache is not set, then we will query the controller, which
    # takes some time.
    def getXYPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            position = self.sendXYCommand(b'POS?', 2, False)
            y, x = position.split(b'\n', maxsplit=2)[:2]
            # Positions are in millimeters, and we need microns.
            x = float(x.split(b'=')[1]) * 1000 * self.axisSignMapper[0]
            y = float(y.split(b'=')[1]) * 1000 * self.axisSignMapper[1]
            self.xyPositionCache = (x, y)
        if axis is None:
            return self.xyPositionCache
        return self.xyPositionCache[axis]


    def makeInitialPublications(self):
        self.sendXYPositionUpdates()


    ## Debugging function: extract all valid parameters from the XY controller.
    def listXYParams(self):
        # Don't use sendXYCommand here because its error handling doesn't
        # deal with HPA?'s output properly -- there's an extra blank line
        # that makes it think output is done when it actually isn't.
        self.xyConnection.write(b'HPA?\n')
        lines = b''
        output = None
        
        while output or len(lines) < 1000:
            output = self.xyConnection.read(100)
            lines += output
        lines = lines.split(b'\n')
        handle = open('params.txt', 'w')
        for line in lines:
            if b'0x' in line:
                # Parameter line
                param = line.split(b'=')[0]
                desc = line.split(b'\t')[5]
                for axis in (1, 2):
                    val = self.sendXYCommand(b'SPA? %d %s' % (axis, param))
                    # Note val has a newline at the end here.
                    handle.write("%s (%s): %s" % (desc, param, val.decode()))
            else:
                # Lines at the beginning/end don't have parameters in them.
                handle.write(line)
        handle.write(b'\n\n')
        handle.close()


    ## Debugging function: test doBoxesIntersect().
    def testBoxIntersect(self):
        for items in [
                [(0, 0), (10, 10), ((5, 5), (15, 15)), True],
                [(5, 5), (15, 5), ((0, 0), (10, 10)), True],
                [(5, 5), (5, 15), ((0, 0), (10, 10)), True],
                [(0, 0), (2, 2), ((6, 6), (8, 8)), False]]:
            print (items)
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
