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

import events
import gui.toggleButton
import util.threads

## This module creates the "status lights" window which tells the user
# various information about their environment.


class StatusLightsWindow(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title = "Status information",
                style = wx.RESIZE_BORDER | wx.CAPTION | wx.FRAME_TOOL_WINDOW)
        self.panel = wx.Panel(self)

        ## Maps status light names to the lights themselves. Each light is
        # a ToggleButton instance.
        self.nameToLight = {}

        events.subscribe('new status light', self.onNewLight)
        events.subscribe('update status light', self.onNewStatus)

        # Some lights that we know we need.
        self.onNewLight('image count', '')
        self.onNewLight('device waiting', '')
        self.Show()


    ## New light generated; insert it into our panel.
    # Do nothing if the light already exists.
    @util.threads.callInMainThread
    def onNewLight(self, lightName, text, backgroundColor = None):
        if lightName in self.nameToLight:
            return
        if backgroundColor is None:
            backgroundColor = (170, 170, 170)
        light = gui.toggleButton.ToggleButton(parent = self.panel,
                activeColor = backgroundColor, activeLabel = text,
                size = (170, 100))
        # For some reason, using a sizer here causes the lights to be placed
        # on top of each other...so I'm just setting sizes manually. HACK.
        self.nameToLight[lightName] = light
        light.SetPosition((170 * (len(self.nameToLight) - 1), 0))
        self.panel.SetClientSize((170 * len(self.nameToLight), 100))
        self.SetClientSize(self.panel.GetSize())


    ## Update the status light with the specified name. Create the light
    # if it doesn't already exist.
    @util.threads.callInMainThread
    def onNewStatus(self, lightName, text, backgroundColor = None):
        if lightName not in self.nameToLight:
            self.onNewLight(lightName, text, backgroundColor)
        else:
            self.nameToLight[lightName].SetLabel(text)
            if backgroundColor is not None:
                self.nameToLight[lightName].SetBackgroundColour(backgroundColor)
            self.nameToLight[lightName].Refresh()



## Global singleton.
window = None

def makeWindow(parent):
    global window
    window = StatusLightsWindow(parent)
    
