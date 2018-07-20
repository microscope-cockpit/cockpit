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


import wx

from cockpit import depot
from . import deviceHandler

from cockpit import events
import cockpit.gui.guiUtils
import cockpit.gui.keyboard
import cockpit.gui.toggleButton

from cockpit.util.colors import dyeToColor

## This handler is responsible for tracking what kinds of light each camera
# receives, via the drawer system.
class DrawerHandler(deviceHandler.DeviceHandler):
    ## We allow either for a set of pre-chosen filters (via DrawerSettings),
    # or for a more variable approach with callbacks. If callbacks are
    # supplied, they override the DrawerSettings if any. 
    # \param settings A list of DrawerSettings instances.
    # \param settingIndex Index into settings list indicating the current mode.
    def __init__(self, name, groupName, settings = None, settingIndex = None,
                 callbacks = {}):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.DRAWER)
        self.settings = settings
        self.settingIndex = settingIndex
        ## List of ToggleButtons, one per setting.
        self.buttons = []
        # Last thing to do is update UI to show default selections.
        events.subscribe('cockpit initialization complete', self.changeDrawer)


    ## Generate a row of buttons, one for each possible drawer.
    def makeUI(self, parent):
        if not self.settings or len(self.settings) == 1:
            # Nothing to be done here.
            return None
        frame = wx.Frame(parent, title = "Drawers",
                style = wx.RESIZE_BORDER | wx.CAPTION | wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        for setting in self.settings:
            button = cockpit.gui.toggleButton.ToggleButton(
                    label = setting.name, parent = panel, 
                    size = (80, 40))
            button.Bind(wx.EVT_LEFT_DOWN, 
                    lambda event, setting = setting: self.changeDrawer(setting))
            sizer.Add(button)
            self.buttons.append(button)
        panel.SetSizerAndFit(sizer)
        frame.SetClientSize(panel.GetSize())
        frame.SetPosition((2400, 65))
        frame.Show()
        cockpit.gui.keyboard.setKeyboardHandlers(frame)
        return None


    ## Set dye and wavelength on each camera, and update our UI.
    def changeDrawer(self, newSetting=None):
        if newSetting is None:
            ns = self.settings[0]
        else:
            ns = newSetting
            self.settingIndex = self.settings.index(ns)
        for cname in ns.cameraNames:
            h = depot.getHandler(cname, depot.CAMERA)
            h.updateFilter(ns.cameraToDye[cname], ns.cameraToWavelength[cname])
        for i, b in enumerate(self.buttons):
            state = i == self.settingIndex
            b.updateState(state)


## This is a simple container class to describe a single drawer. 
class DrawerSettings:
    ## All parameters except the drawer name are lists, and the lists refer to
    # cameras in the same orders.
    # \param name Name used to refer to the drawer. 
    # \param cameraNames Unique names for each camera. These are the same 
    #        across all drawers.
    # \param dyeNames Names of dyes that roughly correspond to the wavelengths
    #        that the cameras see.
    # \param wavelengths Numerical wavelengths corresponding to the bandpass
    #        filters in front of the cameras.
    def __init__(self, name, cameraNames, dyeNames, wavelengths):
        self.name = name
        self.cameraNames = cameraNames
        self.dyeNames = dyeNames
        self.wavelengths = wavelengths
        self.cameraToDye = dict(zip(cameraNames, dyeNames))
        self.cameraToWavelength = dict(zip(cameraNames, wavelengths))

    def update(self, cameraName, dyeName, wavelength):
        for i, camera in enumerate(self.cameraNames):
            if camera == cameraName:
                self.dyeNames[i] = dyeName
                self.wavelengths[i] = wavelength
                break
        else:
            # Didn't find the camera name.
            self.cameraNames.append(cameraName)
            self.dyeNames.append(dyeName)
            self.wavelengths.append(wavelength)
        self.cameraToDye = dict(zip(self.cameraNames, self.dyeNames))
        self.cameraToWavelength = dict(zip(self.cameraNames, self.wavelengths))
