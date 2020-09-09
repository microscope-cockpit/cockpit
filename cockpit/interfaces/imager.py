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


from cockpit import events
from cockpit.handlers.imager import ImagerHandler
import cockpit.util.threads
import wx

import time
import typing
import traceback

## This module provides an interface for taking images with the current
# active cameras and light sources. It's used only outside of experiment
# mode.


def pauseVideo(func):
    """A wrapper to pause and resume video."""
    def wrapper(*args, **kwargs):
        wasInVideoMode = wx.GetApp().Imager.amInVideoMode
        if wasInVideoMode:
            wx.GetApp().Imager.shouldStopVideoMode = True
            tstart = time.time()
            while wx.GetApp().Imager.amInVideoMode:
                time.sleep(0.05)
                if time.time() > tstart + 1.:
                    print("Timeout pausing video mode - abort and restart.")
                    events.publish(events.USER_ABORT)
                    break
        result = func(*args, **kwargs)
        if wasInVideoMode:
            wx.GetApp().Imager.videoMode()
        return result

    return wrapper


## Simple container class.
class Imager:
    def __init__(self, handlers: typing.Sequence[ImagerHandler]) -> None:
        ## List of Handlers capable of taking images.
        self._imageHandlers = handlers
        ## Set of active cameras, so we can check their framerates.
        self.activeCameras = set()
        events.subscribe(events.CAMERA_ENABLE,
                lambda c, isOn: self.toggle(self.activeCameras, c, isOn))
        ## Set of active light sources, so we can check their exposure times.
        self.activeLights = set()
        events.subscribe(events.LIGHT_SOURCE_ENABLE,
                lambda l, isOn: self.toggle(self.activeLights, l, isOn))
        ## Time of last call to takeImage(), so we can avoid calling it
        # faster than the time it takes to actually collect another image.
        self.lastImageTime = time.time()
        ## Boolean to control activity of the video mode thread.
        self.shouldStopVideoMode = False
        ## Boolean that indicates if we're currently in video mode.
        self.amInVideoMode = False
        events.subscribe(events.USER_ABORT, self.stopVideo)
        # Update exposure times on certain events.
        events.subscribe('light exposure update', self.updateExposureTime)
        events.subscribe(events.LIGHT_SOURCE_ENABLE, lambda *args: self.updateExposureTime())
        events.subscribe(events.CAMERA_ENABLE, lambda *args: self.updateExposureTime())


    ## Update exposure times on cameras.
    @pauseVideo
    def updateExposureTime(self, source=None):
        e_times = [l.getExposureTime() for l in self.activeLights]
        if not e_times:
            return
        e_max = max(e_times)
        [c.setExposureTime(e_max) for c in self.activeCameras]


    ## Add or remove the provided object from the specified set.
    def toggle(self, container, thing, shouldAdd):
        if shouldAdd:
            container.add(thing)
        elif thing in container:
            container.remove(thing)


    ## Take an image.
    # \param shouldBlock True if we want to wait for the cameras and lights
    #        to be ready so we can take the image; False if we don't want to
    #        wait and should just give up if they aren't ready.
    # \param shouldStopVideo True if we should stop video mode. Only really
    #        used by self.videoMode().
    def takeImage(self, shouldBlock = False, shouldStopVideo = True):
        from cockpit.experiment import experiment
        if experiment.isRunning():
            print("Skipping takeImage because an experiment is running.")
            return
        elif len(self.activeCameras) == 0:
            message = ('There are no cameras enabled.')
            wx.MessageBox(message, caption='No cameras active')
            return
        if shouldStopVideo:
            self.stopVideo()
        waitTime = self.getNextImageTime() - time.time()
        if waitTime > 0:
            if shouldBlock:
                time.sleep(waitTime)
            else:
                return
        for handler in self._imageHandlers:
            handler.takeImage()
        self.lastImageTime = time.time()


    ## Video mode: continuously take images at our maximum update rate.
    # We stop whenever the user invokes takeImage() manually or the abort
    # button is pressed. We also limit our image rate if there are any
    # non-room-light light sources to 1 image per second, to avoid excessive
    # sample damage.
    @cockpit.util.threads.callInNewThread
    def videoMode(self):
        if not self.activeCameras:
            # No cameras, no video mode.
            events.publish(cockpit.events.VIDEO_MODE_TOGGLE, False)
            return
        if self.amInVideoMode:
            # Just cancel the current video mode.
            events.publish(cockpit.events.VIDEO_MODE_TOGGLE, False)
            self.stopVideo()
            return

        events.publish(cockpit.events.VIDEO_MODE_TOGGLE, True)
        self.shouldStopVideoMode = False
        self.amInVideoMode = True
        while not self.shouldStopVideoMode:
            if not self.activeLights:
                break
            # HACK: only wait for one camera.
            camera = list(self.activeCameras)[0]
            # Some cameras drop frames, i.e., takeImage() returns but
            # an image is never received.  If that happens, videoMode
            # waits forever since there's no NEW_IMAGE event hence the
            # timeout.  On top of the time to actual acquire the
            # image, we add 5 seconds for any processing and transfer
            # which should be more than enough (see issue #584).
            timeout = 5.0 + ((camera.getExposureTime()
                              + camera.getTimeBetweenExposures()) / 1000)
            try:
                events.executeAndWaitForOrTimeout(
                    events.NEW_IMAGE % (camera.name),
                    self.takeImage, timeout,
                    shouldBlock = True, shouldStopVideo = False)
            except Exception as e:
                print ("Video mode failed:", e)
                events.publish(cockpit.events.VIDEO_MODE_TOGGLE, False)
                traceback.print_exc()
                break
        self.amInVideoMode = False
        events.publish(cockpit.events.VIDEO_MODE_TOGGLE, False)


    ## Stop our video thread, if relevant.
    def stopVideo(self):
        self.shouldStopVideoMode = True


    ## Get the next time it's safe to call takeImage(), based on the
    # cameras' time between images and the light sources' exposure times.
    def getNextImageTime(self):
        camLimiter = 0
        for camera in self.activeCameras:
            camLimiter = max(camLimiter, camera.getTimeBetweenExposures())
        lightLimiter = 0
        for light in self.activeLights:
            lightLimiter = max(lightLimiter, light.getExposureTime())
        # The limiters are in milliseconds; downconvert.
        return self.lastImageTime + (camLimiter + lightLimiter) / 1000.0
