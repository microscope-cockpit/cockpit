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

from cockpit import depot
from cockpit.handlers import deviceHandler
from cockpit import events

import cockpit.util.threads


## This handler is for lightsource toggle buttons and exposure time settings,
# to control if a given illumination source is currently active (and for how
# long).
class LightHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions: 
    # - setEnabled(name, value): Turn this light source on or off.
    # - setExposureTime(name, value): Set the exposure time for this light,
    #   in milliseconds.
    # - getExposureTime(name, value): Get the current exposure time for this
    #   light, in milliseconds.
    # - setExposing(name, isOn): Optional. Sets the light on/off continuously
    #   (i.e. without regard for what the camera(s) are doing). 
    # \param wavelength Wavelength of light the source emits, if appropriate.
    # \param exposureTime Default exposure time.
    # \param trigHandler: Optional. Sets up an auxilliary trigger source.
    # \param trigLine: Optional. May be required by aux. trig. source.

    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    ## Keep track of shutters in class variables.
    __shutterToLights = {} # 1:many
    __lightToShutter = {} # 1:1
    @classmethod
    def addShutter(cls, shutter, lights=[]):
        cls.__shutterToLights[shutter] = set(lights)
        for l in lights:
            cls.__lightToShutter[l] = shutter


    def __init__(self, name, groupName, callbacks, wavelength, exposureTime,
                 trigHandler=None, trigLine=None):
        # Note we assume all light sources are eligible for experiments.
        # However there's no associated callbacks for a light source.
        super().__init__(name, groupName, True, callbacks, depot.LIGHT_TOGGLE)
        self.wavelength = float(wavelength or 0)
        self.defaultExposureTime = exposureTime
        self.exposureTime = exposureTime
        # Current enabled state
        self.state = deviceHandler.STATES.disabled
        # Set up trigger handling.
        if trigHandler and trigLine:
            h = trigHandler.registerDigital(self, trigLine)
            self.triggerNow = h.triggerNow
            if 'setExposing' not in callbacks:
                cb = lambda name, state: trigHandler.setDigital(trigLine, state)
                callbacks['setExposing'] = cb
        else:
            self.triggerNow = lambda: None

        # Most lasers use bulb-type triggering. Ensure they're not left on after
        # an abort event.
        if trigHandler and trigLine:
            onAbort = lambda *args: trigHandler.setDigital(trigLine, False)
            events.subscribe(events.USER_ABORT, onAbort)


    def makeInitialPublications(self):
        # Send state event to set initial state of any controls.
        events.publish(events.DEVICE_STATUS, self, self.state)


    def onSaveSettings(self):
        return {
            "isEnabled": self.getIsEnabled(),
            "exposureTime": self.getExposureTime(),
        }

    def onLoadSettings(self, settings):
        # Only change settings if needed.
        if self.getExposureTime() != settings["exposureTime"]:
            self.setExposureTime(settings["exposureTime"])
        if self.getIsEnabled() != settings["isEnabled"]:
            self.toggleState()


    ## Turn the laser on, off, or set continuous exposure.
    def setEnabled(self, setState):
        if self.state == deviceHandler.STATES.constant != setState:
            if 'setExposing' in self.callbacks:
                self.callbacks['setExposing'](self.name, False)

        if setState == deviceHandler.STATES.constant:
            if self.state == setState:
                # Turn off the light
                self.callbacks['setEnabled'](self.name, False)
                # Update setState since used to set self.state later
                setState = deviceHandler.STATES.disabled
                events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
            else:
                # Turn on the light continuously.
                self.callbacks['setEnabled'](self.name, True)
                if 'setExposing' in self.callbacks:
                    self.callbacks['setExposing'](self.name, True)
                # We indicate that the light source is disabled to prevent
                # it being switched off by an exposure, but this event is
                # used to update controls, so we need to chain it with a
                # manual update.
                events.oneShotSubscribe(events.LIGHT_SOURCE_ENABLE,
                                        lambda *args: self.notifyListeners(self, setState))
                events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
        elif setState == deviceHandler.STATES.enabled:
            self.callbacks['setEnabled'](self.name, True)
            events.publish(events.LIGHT_SOURCE_ENABLE, self, True)
        else:
            self.callbacks['setEnabled'](self.name, False)
            events.publish(events.LIGHT_SOURCE_ENABLE, self, False)
        self.state = setState


    ## Return True if we're enabled, False otherwise.
    def getIsEnabled(self):
        return self.state == deviceHandler.STATES.enabled

    ## Set the light source to continuous exposure, if we have that option.
    @cockpit.util.threads.callInNewThread
    def setExposing(self, args):
        if not self.enableLock.acquire(False):
            return
        self.notifyListeners(self, deviceHandler.STATES.enabling)
        try:
            self.setEnabled(deviceHandler.STATES.constant)
        except Exception as e:
            self.notifyListeners(self, deviceHandler.STATES.error)
            raise Exception('Problem encountered en/disabling %s:\n%s' % (self.name, e))
        finally:
            self.enableLock.release()

    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, value, outermost=True):
        ## Set the exposure time on self and update that on lights
        # that share the same shutter if this is the outermost call.
        # \param value: new exposure time
        # \param outermost: flag indicating that we should update others.
        self.callbacks['setExposureTime'](self.name, value)
        # Publish event to update control labels.
        events.publish('light exposure update', self)
        # Update exposure times for lights that share the same shutter.
        s = self.__class__.__lightToShutter.get(self, None)
        self.exposureTime = value
        if s and outermost:
            if hasattr(s, 'setExposureTime'):
                s.setExposureTime(value)
            for other in self.__class__.__shutterToLights[s].difference([self]):
                other.setExposureTime(value, outermost=False)
                events.publish('light exposure update', other)

    ## Get the current exposure time, in milliseconds.
    @cached
    def getExposureTime(self):
        return self.callbacks['getExposureTime'](self.name)


    ## Simple getter.
    @cached
    def getWavelength(self):
        return self.wavelength


    ## Let them know what wavelength we are.
    def getSavefileInfo(self):
        return str(self.wavelength)
