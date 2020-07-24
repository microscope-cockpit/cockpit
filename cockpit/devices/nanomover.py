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

import re
import time

from cockpit.devices.device import Device
from cockpit import events

import cockpit.interfaces
import cockpit.handlers.genericPositioner
import cockpit.handlers.stagePositioner
import cockpit.util.connection
import cockpit.util.threads
import cockpit.util.userConfig

## TODO: test with hardware.

LIMITS_PAT = r"(?P<limits>\(\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*\,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*\))"

class Nanomover(Device):
    def __init__(self, name, config={}):
        super().__init__(name, config)
        ## Current stage position information.
        self.curPosition = [14500, 14500, 14500]
        ## Connection to the Nanomover controller program.
        self.connection = None
        # Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering (1: Y, 2: X,0: Z)
        self.axisMapper = {0: 0, 1: 1, 2: 2}
        ## Cached copy of the stage's position. Initialized to an impossible
        # value; this will be modified in initialize.
        self.positionCache = (10, 10, 10)
        ## Maps cockpit axis ordering to a +-1 multiplier to apply to motion,
        # since some of our axes are flipped.
        self.axisSignMapper = {0: 1, 1: 1, 2: 1}
        ## Time of last action using the piezo; used for tracking if we should
        # disable closed loop.
        self.timeout = float(config.get('timeout', 0.1))
        try :
            limitString = config.get('softlimits', '')
            parsed = re.search(LIMITS_PAT, limitString)
            if not parsed:
                # Could not parse config entry.
                raise Exception('Bad config: Nanomover Limits.')
                # No transform tuple
            else:
                lstr = parsed.groupdict()['limits']
                self.softlimits=eval(lstr)
                self.safeties=eval(lstr)
        except:
            print ("No softlimits section setting default limits")
            self.softlimits = [[0, 25000],
                               [0, 25000],
                               [7300, 25000]]
            self.safeties = [[0, 25000],
                               [0, 25000],
                               [7300, 25000]]

        # a useful middle position for after a home
        self.middleXY=( (self.safeties[0][1]-self.safeties[0][0])/2.0,
                        (self.safeties[0][1]-self.safeties[0][0])/2.0)
        events.subscribe(events.USER_ABORT, self.onAbort)
        events.subscribe('cockpit initialization complete',
                         self.promptExerciseStage)

        

    def initialize(self):
        self.connection = cockpit.util.connection.Connection(
                'nano', self.ipAddress, self.port)
        self.connection.connect(self.receiveData)
        self.curPosition[:] = self.connection.connection.posXYZ_OMX()
        if self.curPosition == [0,0,0]:
            print ("Homing Nanomover")
            self.connection.connection.startOMX()
            self.home()
            cockpit.interfaces.stageMover.goToXY(self.middleXY, shouldBlock = True)

    ## We want to periodically exercise the XY stage to spread the grease
    # around on its bearings; check how long it's been since the stage was
    # last exercised, and prompt the user if it's been more than a week.
    def promptExerciseStage(self):
        lastExerciseTimestamp = cockpit.util.userConfig.getValue(
                'NanomoverLastExerciseTimestamp', default = 0)
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
            initialPos = tuple(self.positionCache)
#            cockpit.interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            for i in range(5):
                print ("Rep %d of 5..." % i)
                for position in self.softlimits[0:2]:
                    cockpit.interfaces.stageMover.goToXY(position, shouldBlock = True)
            cockpit.interfaces.stageMover.goToXY(self.middleXY, shouldBlock = True)
            cockpit.interfaces.stageMover.goToXY(initialPos, shouldBlock = True)
            print ("Exercising complete. Thank you!")

            cockpit.util.userConfig.setValue('NanomoverLastExerciseTimestamp',
                                             time.time())



    def performSubscriptions(self):
        events.subscribe(events.USER_ABORT, self.onAbort)


    def makeInitialPublications(self):
        self.publishPosition()
        self.sendXYPositionUpdates()

    ## The XY Macro Stage view is painting itself; draw the banned
    # rectangles as pink excluded zones.
#    def onMacroStagePaint(self, stage):
#        glColor3f(1, .6, .6)
#        glBegin(GL_QUADS)
#        for (x1, y1), (x2, y2) in BANNED_RECTANGLES:
#            stage.scaledVertex(x1, y1)
#            stage.scaledVertex(x1, y2)
#            stage.scaledVertex(x2, y2)
#            stage.scaledVertex(x2, y1)
#        glEnd()


    def getHandlers(self):
        result = []
        for axis in range(3):
            lowLimit, highLimit = self.safeties[axis]
            softLowLimit , softHighLimit = self.softlimits[axis]
            result.append(cockpit.handlers.stagePositioner.PositionerHandler(
                "%d nanomover" % axis, "%d stage motion" % axis, False, 
                {'moveAbsolute': self.moveAbsolute, 
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition}, 
                axis, (softLowLimit, softHighLimit), (lowLimit, highLimit)))
        return result


    ## Publish the current stage position.
    def publishPosition(self):
        for axis in range(3):
            events.publish(events.STAGE_MOVER, axis)


    ## Send updates on the XY stage's position, until it stops moving.
    @cockpit.util.threads.callInNewThread
    def sendXYPositionUpdates(self):
        while True:
            prevX, prevY = self.positionCache[:2]
            x, y = self.getPosition(shouldUseCache = False)[:2]
            delta = abs(x - prevX) + abs(y - prevY)
            if delta < 2:
                # No movement since last time; done moving.
                for axis in [0, 1]:
                    events.publish(events.STAGE_STOPPED, '%d nanomover' % axis)
                return
            for axis in [0, 1]:
                events.publish(events.STAGE_MOVER, axis)
            time.sleep(.1)

    def getPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            position = self.connection.connection.posXYZ_OMX()
            x = float(position[self.axisMapper[0]]) * self.axisSignMapper[0]
            y = float(position[self.axisMapper[1]]) * self.axisSignMapper[1]
            z = float(position[self.axisMapper[2]]) * self.axisSignMapper[2]
            self.positionCache = (x, y, z)
        if axis is None:
            return self.positionCache
        return self.positionCache[axis]


    ## Receive information from the Nanomover control program.
    def receiveData(self, *args):
        if args[0] == 'nanoMotionStatus':
            self.curPosition[:] = args[1]
            self.publishPosition()
            if args[-1] == 'allStopped':
                for i in range(3):
                    events.publish(events.STAGE_STOPPED, '%d nanomover' % i)


    ## Move a specific axis to a given position.
    def moveAbsolute(self, axis, pos):
        self.sendXYPositionUpdates()
        self.connection.connection.moveOMX_axis(axis, pos)



    ## Move a specific axis by a given amount.
    def moveRelative(self, axis, delta):
        self.sendXYPositionUpdates()
        self.connection.connection.moveOMX_dAxis(axis, delta)


    ## User clicked the abort button; halt motion.
    def onAbort(self, *args):
        self.connection.connection.stopOMX()

    #function to home stage if needed.
    def home(self):
        #keep a copy of the softlimits.
#        realSoftlimits= copy.copy(self.softlimits)
#        self.softlimits = [[-25000, 25000],
#                           [-25000, 25000],
#                           [7300, 50000]]
        #home the stage which moves to lrage negative positon until it 
        #hits the hard limit switch 
        self.connection.connection.findHome_OMX()
        self.sendXYPositionUpdates()
        self.positionCache = self.getPosition(shouldUseCache = False)
        #reset softlimits to their original value
#        self.softlimits=realSoftlimits

