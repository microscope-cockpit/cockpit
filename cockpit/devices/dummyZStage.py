#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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


## This module creates a simple stage-positioning device.

from cockpit import depot
from cockpit.devices import device
from cockpit import events
import cockpit.handlers.stagePositioner


class DummyZStage(device.Device):
    def __init__(self, name='dummy Z stage', config={}):
        super().__init__(name, config)
        self.curPosition = 100
        self.deviceType = "stage positioner"
        # Is this device in use?
        self.active = False
        self.axes = [2]


    def initialize(self):
        # At this point we would normally get the true stage position from
        # the actual device, but of course we have no such device.
        events.subscribe(events.USER_ABORT, self.onAbort)
        self.active = True
        pass
        

    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        axis = 2
        minVal = 0
        maxVal = 25000
        handler = cockpit.handlers.stagePositioner.PositionerHandler(
            "%d dummy mover" % axis, "%d stage motion" % axis, True, 
            {'moveAbsolute': self.moveAbsolute,
                'moveRelative': self.moveRelative, 
                'getPosition': self.getPosition, 
                'getMovementTime': self.getMovementTime,
                'cleanupAfterExperiment': self.cleanup},
                axis, (minVal, maxVal), (minVal, maxVal))
        result.append(handler)
        return result


    ## Publish our current position.
    def makeInitialPublications(self):
        if not self.active:
            return
        axis = 2
        events.publish(events.STAGE_MOVER, axis)


    ## User clicked the abort button; stop moving.
    def onAbort(self):
        axis = 2
        events.publish(events.STAGE_STOPPED, '%d dummy mover' % axis)


    ## Move the stage piezo to a given position.
    def moveAbsolute(self, axis, pos):
        self.curPosition = pos
        # Dummy movers finish movement immediately.
        events.publish(events.STAGE_MOVER, axis)
        events.publish(events.STAGE_STOPPED, '%d dummy mover' % axis)


    ## Move the stage piezo by a given delta.
    def moveRelative(self, axis, delta):
        self.curPosition += delta
        # Dummy movers finish movement immediately.
        events.publish(events.STAGE_MOVER, axis)
        events.publish(events.STAGE_STOPPED, '%d dummy mover' % axis)


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


    ## Cleanup after an experiment. For a real mover, this would probably 
    # just mean making sure we were back where we were before the experiment
    # started.
    def cleanup(self, axis, isCleanupFinal):
        pass
