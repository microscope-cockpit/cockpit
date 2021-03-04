#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Thomas Park <thomasparks@outlook.com>
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

from cockpit import depot
from cockpit.handlers import deviceHandler
from cockpit import events
import time


## This handler is for stage positioner devices.
class PositionerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - moveAbsolute(axis, position): Move the axis to the
    #   given position, in microns.
    # - moveRelative(axis, delta): Move the axis by the specified
    #   delta, in microns.
    # - getPosition(axis): Get the position for the specified axis.
    # Additionally, if the device is to be used in experiments, it must have:
    # - getMovementTime(axis, start, end): Get the amount of time it takes to 
    #   move from start to end and then stabilize.
    # \param axis A numerical indicator of the axis (0 = X, 1 = Y, 2 = Z).
    # \param hardLimits A (minPosition, maxPosition) tuple indicating
    #        the device's hard motion limits.
    # \param softLimits Default soft motion limits for the device. Defaults
    #        to the hard limits.

    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    def __init__(self, name, groupName, isEligibleForExperiments, callbacks, 
            axis, hardLimits, softLimits = None):
        super().__init__(name, groupName, isEligibleForExperiments, callbacks,
                         depot.STAGE_POSITIONER)
        self.axis = axis
        self.hardLimits = hardLimits
        if softLimits is None:
            softLimits = hardLimits
        elif min(softLimits) < min(hardLimits) or max(softLimits) > max(hardLimits):
            raise RuntimeError('Soft limits {} for the PositionerHandler were outside the \
                               Range of hard limits {}'.format(softLimits, hardLimits))
            
        # Cast to a list since we may need to modify these later.
        self.softLimits = list(softLimits)


    ## Handle being told to move to a specific position.
    def moveAbsolute(self, pos):
        if self.softLimits[0] <= pos <= self.softLimits[1]:
            self.callbacks['moveAbsolute'](self.axis, pos)
        else:
            raise RuntimeError("Tried to move %s " % (self.name) +
                    "outside soft motion limits (target %.2f, limits [%.2f, %.2f])" %
                    (pos, self.softLimits[0], self.softLimits[1]))


    ## Handle being told to move by a specific delta.
    def moveRelative(self, delta):
        target = self.callbacks['getPosition'](self.axis) + delta
        if self.softLimits[0] <= target <= self.softLimits[1]:
            self.callbacks['moveRelative'](self.axis, delta)
        else:
            raise RuntimeError("Tried to move %s " % (self.name) +
                    "outside soft motion limits (target %.2f, limits [%.2f, %.2f])" %
                    (target, self.softLimits[0], self.softLimits[1]))


    ## Retrieve the current position.
    def getPosition(self):
        return self.callbacks['getPosition'](self.axis)


    ## Simple getter.
    def getHardLimits(self):
        return self.hardLimits


    ## Simple getter.
    def getSoftLimits(self):
        return self.softLimits


    ## Set a soft limit, either min or max.
    def setSoftLimit(self, value, isMax):
        if isMax and value > self.hardLimits[1]:
            raise RuntimeError("Attempted to set soft motion limit of %s, exceeding our hard motion limit of %s" % (value, self.hardLimits[1]))
        elif not isMax and value < self.hardLimits[0]:
            raise RuntimeError("Attempted to set soft motion limit of %s, lower than our hard motion limit of %s" % (value, self.hardLimits[0]))
        self.softLimits[int(isMax)] = value

    
    ## Return the amount of time it'd take us to move the specified distance,
    # and the amount of time needed to stabilize after reaching that point.
    # Only called if this device is experiment-eligible.
    def getMovementTime(self, start, end):
        if self.isEligibleForExperiments:
            # if (start < self.softLimits[0] or start > self.softLimits[1] or 
            #         end < self.softLimits[0] or end > self.softLimits[1]):
            #     raise RuntimeError("Experiment tries to move [%s] from %.2f to %.2f, outside motion limits (%.2f, %.2f)" % (self.name, start, end, self.softLimits[0], self.softLimits[1]))
            # return self.callbacks['getMovementTime'](self.axis, start, end)
            return self.getDeltaMovementTime(end - start)
        raise RuntimeError("Called getMovementTime on non-experiment-eligible positioner [%s]" % self.name)


    @cached
    def getDeltaMovementTime(self, delta):
        return self.callbacks['getMovementTime'](self.axis, 0., delta)


    ## Register this handler with an analogue source.
    def connectToAnalogSource(self, source, line, offset, gain):
        h = source.registerAnalog(self, line, offset, gain)
        # Movements are handled by the analogue handler, but need to wrap to
        # publish postion update and stage stop events.
        def wrapMoveFunc(f):
            def call(x, arg):
                f(arg)
                time.sleep(sum(self.getMovementTime(0, arg)))
                events.publish(events.STAGE_MOVER, x)
                events.publish(events.STAGE_STOPPED, self.name)
            return call

        self.callbacks['moveAbsolute'] = wrapMoveFunc(h.moveAbsolute)
        self.callbacks['moveRelative'] = wrapMoveFunc(h.moveRelative)

        # Sensorless devices will infer position from analogue output.
        # Those with sensors should have already specified this callback.
        if self.callbacks.get('getPosition') is None:
            self.callbacks['getPosition'] = lambda x: h.getPosition()
