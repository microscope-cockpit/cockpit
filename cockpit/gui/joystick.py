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


from operator import sub
import sys
import time
import wx
import wx.adv

# Define a button comparison function that supports the different
# enumeration schemes on Windows and Linux as at wxWidgets version 3.1.2.
# Currently, different platforms enumerate changed buttons as follows:
#   win32    0b1, 0b10, 0b100, ...
#   linux    0, 1, 2, 3, ...
#   mac      1, 2, 3, 4, ...
# It is likely that one or the other scheme will be chosen in the near
# future, but it may take several months for this to roll out to
# wxPython.

if sys.platform == 'win32':
    buttonTest = lambda variable, constant: variable & (1 << constant)
elif sys.platform == 'linux':
    buttonTest = lambda a, b: a == b
else:
    buttonTest = lambda a, b: a-1 ==  b


# Stick movement threshold
_CLICKMS = 200
_THRESHOLD = 300

# Joystick behaviour
#   move, no button     - pan mosaic window
#   move, button 0 held - move XY stage
#   move, button 1 held - move Z stage
#   press button 0      - centre stage in mosaic window
#   press button 1      - toggle mover
#   press button 2      - snap image (implicit stop video mode)
#   hold button 2      - start video mode
#   press button 3      - start mosaic

# Can't use `from cockpit.interfaces.imager import imager`
# here as imager is None at time of import, so must either:
#  * import module and use imager.imager,
#  * or 'from ... import imager' wherever it's used.
import cockpit.gui.mosaic.window as mosaic


class Joystick:
    def __init__(self, window):
        if sys.platform == 'darwin':
            return None
        self._stick = wx.adv.Joystick()
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
        if buttonTest(self._stick.ButtonState, button):
            func()


    def _onButtonDown(self, event):
        # Old MSW joystick implementation did not populate timestamps,
        # so fallback to time.time().
        ts = event.GetTimestamp() or (time.time() * 1000)
        self._buttonDownTimes[event.ButtonChange] = ts
        if buttonTest(event.ButtonChange, 2):
            wx.CallLater(_CLICKMS, self._longPress, 2,
                         wx.GetApp().Imager.videoMode)


    def _onButtonUp(self, event):
        ts = event.GetTimestamp() or (time.time() * 1000)
        # Long press or timeout
        if ts - self._buttonDownTimes[event.ButtonChange] > _CLICKMS:
            return
        # Short press
        if buttonTest(event.ButtonChange, 0):
            mosaic.window.centerCanvas()
        elif buttonTest(event.ButtonChange, 1):
            from cockpit.interfaces.stageMover import changeMover
            changeMover()
        elif buttonTest(event.ButtonChange, 2):
            wx.GetApp().Imager.takeImage()
        elif buttonTest(event.ButtonChange, 3):
             mosaic.window.toggleMosaic()


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
        if buttonTest(event.ButtonState, 0):
            moveRelative([-0.01*d for d in delta] + [0], False)
        elif buttonTest(event.ButtonState, 1):
            moveRelative([0, 0, -0.01*delta[1]], False)
        else:
            mosaic.window.canvas.dragView(tuple(0.01*d for d in delta))
