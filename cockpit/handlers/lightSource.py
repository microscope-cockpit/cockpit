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


import wx

from cockpit import depot
from . import deviceHandler
from cockpit import events

import cockpit.gui.dialogs.getNumberDialog
import cockpit.gui.guiUtils
import cockpit.gui.toggleButton
import cockpit.util.threads

## List of exposure times to allow the user to set.
EXPOSURE_TIMES = [1, 5] + list(range(10, 100, 10)) + list(range(100, 1100, 100))

## Color to use for light sources that are in continuous exposure mode.
CONTINUOUS_COLOR = (255, 170, 0)

## Size of the button we make in the UI.
BUTTON_SIZE = (120, 40)

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
        deviceHandler.DeviceHandler.__init__(self, name, groupName, True, 
                callbacks, depot.LIGHT_TOGGLE)
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


        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        # Most lasers use bulb-type triggering. Ensure they're not left on after
        # an abort event.
        if trigHandler and trigLine:
            onAbort = lambda *args: trigHandler.setDigital(trigLine, False)
            events.subscribe('user abort', onAbort)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = {
            'isEnabled': self.getIsEnabled(),
            'exposureTime': self.getExposureTime()}


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            #Only chnbage settings if needed.
            if self.getExposureTime != settings[self.name]['exposureTime']:
                self.setExposureTime(settings[self.name]['exposureTime'])
            if self.getIsEnabled != settings[self.name]['isEnabled']:
                self.setEnabled(settings[self.name]['isEnabled'])


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
                events.publish('light source enable', self, False)
            else:
                # Turn on the light continuously.
                self.callbacks['setEnabled'](self.name, True)
                if 'setExposing' in self.callbacks:
                    self.callbacks['setExposing'](self.name, True)
                # We indicate that the light source is disabled to prevent
                # it being switched off by an exposure, but this event is
                # used to update controls, so we need to chain it with a
                # manual update.
                events.oneShotSubscribe('light source enable',
                                        lambda *args: self.notifyListeners(self, setState))
                events.publish('light source enable', self, False)
        elif setState == deviceHandler.STATES.enabled:
            self.callbacks['setEnabled'](self.name, True)
            events.publish('light source enable', self, True)
        else:
            self.callbacks['setEnabled'](self.name, False)
            events.publish('light source enable', self, False)
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


    ## Return True iff we are in continuous-exposure mode. We use the color
    # of our button as the indicator for that state.
    def getIsExposingContinuously(self):
        return self.state == deviceHandler.STATES.constant


    ## Make a menu to let the user select the exposure time.
    def makeMenu(self, parent):
        menu = wx.Menu()
        for i, value in enumerate(EXPOSURE_TIMES):
            menu.Append(i + 1, str(value))
            parent.Bind(wx.EVT_MENU,  lambda event, value = value: self.setExposureTime(value), id= i + 1)
        menu.Append(len(EXPOSURE_TIMES) + 1, '...')
        parent.Bind(wx.EVT_MENU,  lambda event: self.setCustomExposureTime(parent), id= len(EXPOSURE_TIMES) + 1)
        cockpit.gui.guiUtils.placeMenuAtMouse(parent, menu)


    ## Pop up a dialog to let the user input a custom exposure time.
    def setCustomExposureTime(self, parent):
        value = cockpit.gui.dialogs.getNumberDialog.getNumberFromUser(
                parent, "Input an exposure time:",
                "Exposure time (ms):", self.getExposureTime())
        self.setExposureTime(float(value))


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

