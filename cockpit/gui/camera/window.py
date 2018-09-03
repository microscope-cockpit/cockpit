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
from cockpit import events
import cockpit.gui.keyboard
import cockpit.util.threads
import cockpit.gui.viewFileDropTarget
from . import viewPanel



## This class provides a grid of camera displays.
class CamerasWindow(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title = "Camera views",
                          style=wx.FRAME_NO_TASKBAR | wx.CAPTION)
        
        self.numCameras = len(depot.getHandlersOfType(depot.CAMERA))

        self.panel = wx.Panel(self)

        # Make a 2xN grid of camera canvases, with menus above for selecting
        # which camera to use in that location.
        self.sizer = wx.FlexGridSizer(round(self.numCameras//2 + .5), 2, 5, 5)
        ## List of ViewPanels we contain.
        self.views = []
        for i in range(self.numCameras):
            view = viewPanel.ViewPanel(self.panel)
            self.views.append(view)

        self.SetPosition((675, 280))

        events.subscribe("camera enable", self.onCameraEnableEvent)
        events.subscribe("image pixel info", self.onImagePixelInfo)
        cockpit.gui.keyboard.setKeyboardHandlers(self)

        self.Bind(wx.EVT_CLOSE, self.onClose)

        self.resetGrid()
        self.SetDropTarget(cockpit.gui.viewFileDropTarget.ViewFileDropTarget(self))


    ## The window is closed; use that as a proxy for closing the program,
    # even though we aren't the main window.
    def onClose(self, event):
        events.publish('program exit')
        event.Skip()


    @cockpit.util.threads.callInMainThread
    def onCameraEnableEvent(self, camera, enabled):
        activeViews = [view for view in self.views if view.getIsEnabled()]
        if enabled and camera not in [view.curCamera for view in activeViews]:
            inactiveViews = set(self.views).difference(activeViews)
            inactiveViews.pop().enable(camera)
        elif not(enabled):
            for view in activeViews:
                if view.curCamera is camera:
                    view.disable()
        self.resetGrid()


    ## When cameras are enabled/disabled, we resize the UI to suit. We want
    # there to always be at least one unused ViewPanel the user can use to 
    # enable a new camera, but ideally there should be as few as possible, 
    # to conserve screen real estate.
    def resetGrid(self):
        activeViews = []
        inactiveViews = []
        for view in self.views:
            view.Hide()
            if view.getIsEnabled():
                activeViews.append(view)
            else:
                inactiveViews.append(view)

        # Remake the sizer, adding all active views to it first.
        self.sizer.Clear()
        for view in activeViews:
            self.sizer.Add(view)
            view.Show()
        for view in inactiveViews:
            self.sizer.Add(view)
            if view is inactiveViews[0]:
                view.Show()
                # Other inactive views are hidden.
        self.sizer.Layout()
        self.panel.SetSizerAndFit(self.sizer)
        self.SetClientSize(self.panel.GetSize())


    ## Received information on the pixel under the mouse; update our title
    # to include that information.
    def onImagePixelInfo(self, coords, value):
        self.SetTitle("Camera views    (%d, %d): %d" % (coords[0], coords[1], value))


    ## Rescale each camera view.
    def rescaleViews(self):
        for view in self.views:
            if view.getIsEnabled():
                view.canvas.resetPixelScale()




## Global window singleton.
window = None

def makeWindow(parent):
    global window
    window = CamerasWindow(parent)
    window.Show()


## Simple passthrough.
def rescaleViews():
    window.rescaleViews()


## Retrieve the black- and white-points for a given camera's display.
def getCameraScaling(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getScaling()
    raise RuntimeError("Tried to get camera scalings for non-active camera [%s]" % camera.name)


## As above, but get the relative values used to generate the black/whitepoints.
def getRelativeCameraScaling(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getRelativeScaling()
    raise RuntimeError("Tried to get camera scalings for non-active camera [%s]" % camera.name)



## Retrieve the image currently displayed by the specified camera.
def getImageForCamera(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getPixelData()
