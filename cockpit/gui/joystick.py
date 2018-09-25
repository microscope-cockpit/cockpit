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

from operator import sub, lt
import time
import wx
import wx.adv

# Stick movement threshold
_CLICKMS = 200
_THRESHOLD = 300

# Joystick behaviour
#   move, no button     - pan mosaic window
#   move, button 1 held - move XY stage
#   move, button 2 held - move Z stage
#   press button 1      - centre stage in mosaic window
#   press button 2      - toggle mover
#   press button 3      - snap image (implicit stop video mode)
#   hold button 3       - start video mode
#   press button 4      - start mosaic

# Can't use `from cockpit.interfaces.imager import imager`
# here as imager is None at time of import, so must either:
#  * import module and use imager.imager,
#  * or 'from ... import imager' wherever it's used.
import cockpit.interfaces.imager as imager
import cockpit.gui.mosaic.window as mosaic


class Joystick(object):
    def __init__(self, window):
        self._stick = wx.adv.Joystick()
        self._numsticks = self._stick.GetNumberJoysticks()
        self._stick.SetCapture(window, 50)
        # Stick should be calibrated in the OS rather than correcting
        # for any offset from centre here.
        self._centre = ( (self._stick.XMin + self._stick.XMax) // 2,
                        (self._stick.YMin + self._stick.YMax) // 2)
        self._buttonDownTimes = {}
        window.Bind(wx.EVT_JOY_MOVE, self._onMoveEvent)
        window.Bind(wx.EVT_JOY_BUTTON_DOWN, self._onButtonDown)
        window.Bind(wx.EVT_JOY_BUTTON_UP, self._onButtonUp)


    def _longPress(self, button, func):
        if self._stick.ButtonState & button:
            func()


    def _onButtonDown(self, event):
        # Old MSW joystick implementation did not populate timestamps,
        # so fallback to time.time().
        ts = event.GetTimestamp() or (time.time() * 1000)
        self._buttonDownTimes[event.ButtonChange] = ts
        if event.ButtonChange & 0b100:
            wx.CallLater(_CLICKMS, self._longPress, 0b100, imager.imager.videoMode)


    def _onButtonUp(self, event):
        ts = event.GetTimestamp() or (time.time() * 1000)
        # Long press or timeout
        if ts - self._buttonDownTimes[event.ButtonChange] > _CLICKMS:
            return
        # Short press
        if event.ButtonChange & 0b1:
            mosaic.window.centerCanvas()
        elif event.ButtonChange & 0b10:
            from cockpit.interfaces.stageMover import changeMover
            changeMover()
        elif event.ButtonChange & 0b100:
            imager.imager.takeImage()
        # elif event.ButtonChange & 0b1000:
        #     mosaic.window.toggleMosaic()


    def _onMoveEvent(self, event):
        from cockpit.interfaces.stageMover import moveRelative

        delta = tuple(map(sub, event.Position, self._centre))
        absdelta = map(abs, delta)
        if all([d < _THRESHOLD for d in absdelta]):
            if event.ZPosition > _THRESHOLD:
                mosaic.window.canvas.multiplyZoom(0.99)
            elif event.ZPosition < -_THRESHOLD:
                mosaic.window.canvas.multiplyZoom(1.01)
            return
        if event.ButtonState == 0b1:
            moveRelative([-0.01*d for d in delta] + [0], False)
        elif event.ButtonState == 0b10:
            moveRelative([0, 0, -0.01*delta[1]], False)
        else:
            mosaic.window.canvas.dragView(tuple(0.01*d for d in delta))