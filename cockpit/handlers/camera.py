#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
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

import decimal

from cockpit import depot
from cockpit.handlers import deviceHandler
from cockpit import events
import cockpit.handlers.imager
import cockpit.interfaces.imager
import cockpit.util.colors


## Available trigger modes for triggering the camera.
# Trigger at the end of an exposure; trigger before the exposure;
# trigger for the duration of the exposure.
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION, TRIGGER_SOFT, TRIGGER_DURATION_PSEUDOGLOBAL) = range(5)

## This handler is for cameras, of course. Cameras provide images to the 
# microscope, and are assumed to be usable during experiments. 
class CameraHandler(deviceHandler.DeviceHandler):
    ## Create the Handler. 
    # callbacks should fill in the following functions:
    # - setEnabled(name, shouldEnable): Turn the camera "on" or "off".
    # - getImageSize(name): Return a (width, height) tuple describing the size
    #   in pixels of the image the camera takes.
    # - getTimeBetweenExposures(name, isExact): Return the minimum time between
    #   exposures for this camera, in milliseconds. If isExact is set, returns
    #   a decimal.Decimal instance.
    # - setExposureTime(name, time): Change the camera's exposure time to
    #   the specified value, in milliseconds.
    # - getExposureTime(name, isExact): Returns the time in milliseconds that
    #   the camera is set to expose for when triggered. If isExact is set,
    #   returns a decimal.Decimal instance.
    # - prepareForExperiment(name, experiment): Get the camera ready for an
    #   experiment.
    # - Optional: getMinExposureTime(name): returns the minimum exposure time
    #   the camera is capable of performing, in milliseconds. If not available,
    #   0ms is used.
    # \param exposureMode One of TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION
    #   or TRIGGER_DURATION_PSEUDOGLOBAL. The first two are for external-trigger
    #   cameras, which may be frame-transfer (trigger at end of exposure, and expose
    #   continuously) or not (trigger at beginning of exposure and expose for
    #   a pre-configured duration). The last two are for external-exposure cameras,
    #   which expose for as long as you tell them to, based on the TTL line.
    #   The TRIGGER_DURATION_PSEUDOGLOBAL is for using the rolling shutter and we
    #   only want to excite the sample in the time that all of the pixels are
    #   exposed.
    # \param minExposureTime Minimum exposure duration, in milliseconds.
    #   Typically only applicable if doExperimentsExposeContinuously is True.
    
    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    def __init__(self, name, groupName, callbacks, exposureMode,
                 trigHandler=None, trigLine=None):
        # Note we assume that cameras are eligible for experiments.
        super().__init__(name, groupName, True, callbacks, depot.CAMERA)
        ## True if the camera is currently receiving images.
        self.isEnabled = False
        self._exposureMode = exposureMode
        self.wavelength = None
        self.dye = None
        # Set up trigger handling.
        if trigHandler and trigLine:
            h = trigHandler.registerDigital(self, trigLine)
            self.triggerNow = h.triggerNow
        else:
            softTrigger = self.callbacks.get('softTrigger', None)
            self.triggerNow = lambda: softTrigger
            if softTrigger:
                depot.addHandler(cockpit.handlers.imager.ImagerHandler(
                    "%s imager" % name, "imager",
                    {'takeImage': softTrigger}))


    def onSaveSettings(self):
        return self.getIsEnabled()

    def onLoadSettings(self, settings):
        # Only change state if we need to as this is slow.
        if self.getIsEnabled() != settings:
            self.toggleState()

    @property
    def color(self):
        if self.wavelength is not None:
            return cockpit.util.colors.wavelengthToColor(self.wavelength, 0.8)
        else:
            return (127,)*3

    @property
    def descriptiveName(self):
        if self.dye is not None:
            return ("%s (%s)" % (self.name, self.dye))
        else:
            return self.name

    @property
    def exposureMode(self):
        return self._exposureMode

    @exposureMode.setter
    def exposureMode(self, triggerType):
        """Set exposure mode."""
        self._exposureMode = triggerType


    def updateFilter(self, dye, wavelength=None):
        ## Update the filter for this camera.
        self.dye = dye
        self.wavelength = wavelength
        events.publish('filter change')


    ## Invoke our callback, and let everyone know that a new camera is online.
    @cockpit.interfaces.imager.pauseVideo
    @reset_cache
    def setEnabled(self, shouldEnable = True):
        try:
            self.isEnabled = self.callbacks['setEnabled'](self.name, shouldEnable)
        except:
            self.isEnabled = False
            raise
        if self.isEnabled != shouldEnable:
            raise Exception("Problem enabling device with handler %s" % self)
        # Subscribe / unsubscribe to the prepare-for-experiment event.
        func = [events.unsubscribe, events.subscribe][shouldEnable]
        func(events.PREPARE_FOR_EXPERIMENT, self.prepareForExperiment)
        events.publish(events.CAMERA_ENABLE, self, self.isEnabled)


    ## Return self.isEnabled.
    def getIsEnabled(self):
        return self.isEnabled


    ## Return the size, in pixels, of images we generated.
    def getImageSize(self):
        return self.callbacks['getImageSize'](self.name)


    ## Return the amount of time, in milliseconds, that must pass after
    # ending one exposure before another can be started.
    # If isExact is specified, then we return a decimal.Decimal value instead
    # of a raw floating point value.
    @cached
    def getTimeBetweenExposures(self, isExact = False):
        return self.callbacks['getTimeBetweenExposures'](self.name, isExact)


    ## Return the minimum allowed exposure time, in milliseconds.
    @cached
    def getMinExposureTime(self, isExact = False):
        val = 0
        if 'getMinExposureTime' in self.callbacks:
            val = self.callbacks['getMinExposureTime'](self.name)
        if isExact:
            return decimal.Decimal(val)
        return val


    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, time):
        return self.callbacks['setExposureTime'](self.name, time)


    ## Return the camera's currently-set exposure time, in milliseconds.
    # If isExact is specified, then we return a decimal.Decimal value instead
    # of a raw floating point value.
    @cached
    def getExposureTime(self, isExact = False):
        return self.callbacks['getExposureTime'](self.name, isExact)

    ## Do any necessary preparation for the camera to participate in an 
    # experiment.
    @reset_cache
    def prepareForExperiment(self, experiment):
        return self.callbacks['prepareForExperiment'](self.name, experiment)


    ## Simple getter.
    def getExposureMode(self):
        return self.exposureMode
