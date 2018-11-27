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


import numpy
import time
import traceback
import wx

from cockpit import depot
from cockpit import events
import cockpit.util.threads
import cockpit.gui.guiUtils
import cockpit.gui.imageViewer.viewCanvas
import cockpit.interfaces.stageMover
import cockpit.interfaces.imager


## Default viewer dimensions.
(VIEW_WIDTH, VIEW_HEIGHT) = (512, 552)


## This class provides an interface for a single camera. It includes a
# button at the top to select which camera to use, a viewing area to display
# the image the camera sees, and a histogram at the bottom.
class ViewPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)

        ## Handle of the current camera we're controlling.
        self.curCamera = None

        columnSizer = wx.BoxSizer(wx.VERTICAL)
        ## Clickable text box showing the name of the currently-selected
        # camera.
        self.selector = wx.StaticText(self,
                style = wx.RAISED_BORDER | wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE, 
                size = (VIEW_WIDTH, 30))
        self.selector.Bind(wx.EVT_LEFT_DOWN, self.onSelector)
        self.selector.SetDoubleBuffered(True)

        columnSizer.Add(self.selector, 0)

        ## Panel for holding our canvas.
        self.canvasPanel = wx.Panel(self)
        self.canvasPanel.SetMinSize((VIEW_WIDTH, VIEW_HEIGHT))
        columnSizer.Add(self.canvasPanel)

        self.SetSizerAndFit(columnSizer)

        ## Canvas we paint the camera's view onto. Created when we connect a
        # camera, and destroyed after.
        self.canvas = None

        self.disable()
        # We need to respond to this event after the cameras do, since we
        # need them to have gotten their new names.
        events.subscribe("filter change", self.onFilterChange, priority = 1000)


    ## User interacted with our current image; on double-clicks we center
    # the display on the mouse.
    def onMouse(self, event):
        if event.LeftDClick():
            x, y = event.GetPosition()
            sizeX, sizeY = self.canvas.GetSize()
            sizeY -= cockpit.gui.imageViewer.viewCanvas.HISTOGRAM_HEIGHT
            pixelSize = depot.getHandlersOfType(depot.OBJECTIVE)[0].getPixelSize()
            dx = ((sizeX / 2) - x) * pixelSize
            dy = ((sizeY / 2) - y) * pixelSize
            #Need to see if the current movers have xy capbility
            positions = cockpit.interfaces.stageMover.getAllPositions()
            handler = cockpit.interfaces.stageMover.mover.curHandlerIndex
            if ((positions[handler][0] == None) or ( positions[handler][1] == None)):
                #We dont have an x or y axis so use the main handler
                originalMover= cockpit.interfaces.stageMover.mover.curHandlerIndex
                cockpit.interfaces.stageMover.mover.curHandlerIndex = 0
                cockpit.interfaces.stageMover.moveRelative((dx, dy, 0))
                cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover
            else:
               cockpit.interfaces.stageMover.moveRelative((dx, dy, 0))
        else:
            event.Skip()


    ## User clicked on the selector. Pop up a menu to let them either activate
    # a camera or, if we're already activated, deactivate the current one.
    # We also let them set the camera's readout size here, if a camera is
    # active.
    def onSelector(self, event):
        menu = wx.Menu()
        if self.curCamera is not None:
            item = menu.Append(-1, "Disable %s" % self.curCamera.descriptiveName)
            self.Bind(wx.EVT_MENU, lambda event: self.curCamera.setEnabled(False), item)
            menu.InsertSeparator(1)
            items = self.canvas.getMenuActions()
            for label, action in items:
                item = menu.Append(-1, label)
                self.Bind(wx.EVT_MENU,
                        lambda event, action = action: action(), item)
            menu.InsertSeparator(len(items) + 2)
            for size in self.curCamera.getImageSizes():
                item = menu.Append(-1, "Set image size to %s" % str(size))
                self.Bind(wx.EVT_MENU,
                        lambda event, size = size: self.curCamera.setImageSize(size),
                        item)                
        else:
            # Get all inactive cameras.
            cameras = depot.getHandlersOfType(depot.CAMERA)
            cameras.sort(key = lambda c: c.descriptiveName)
            for camera in cameras:
                if not camera.getIsEnabled():
                    item = menu.Append(-1, "Enable %s" % camera.descriptiveName)
                    self.Bind(wx.EVT_MENU, 
                            lambda event, cam=camera: cam.setEnabled(True), item)
        cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)


    ## Deactivate the view.
    def disable(self):
        self.selector.SetLabel("No camera")
        self.selector.SetBackgroundColour((180, 180, 180))
        self.selector.Refresh()
        if self.curCamera is not None:
            # Wrap this in a try/catch since it will fail if the initial
            # camera enabling failed.
            events.unsubscribe("new image %s" % self.curCamera.name, self.onImage)
            self.curCamera = None
        if self.canvas is not None:
            # Destroy the canvas.
            self.canvas.clear(shouldDestroy = True)
            self.canvas = None


    ## Activate the view and connect to a data source.
    def enable(self, camera):
        self.selector.SetLabel(camera.descriptiveName)
        self.selector.SetBackgroundColour(camera.color)
        self.selector.Refresh()
        self.curCamera = camera

        # NB the 512 here is the largest texture size our graphics card can
        # gracefully handle.
        self.canvas = cockpit.gui.imageViewer.viewCanvas.ViewCanvas(self.canvasPanel,
                512, size = (VIEW_WIDTH, VIEW_HEIGHT),
                mouseHandler = self.onMouse)
        self.canvas.SetSize((VIEW_WIDTH, VIEW_HEIGHT))
        self.canvas.resetView()

        # Subscribe to new image events only after canvas is prepared.
        events.subscribe("new image %s" % self.curCamera.name, self.onImage)

    ## React to the drawer changing, by updating our labels and colors.
    @cockpit.util.threads.callInMainThread
    def onFilterChange(self):
        if self.getIsEnabled():
            self.selector.SetLabel(self.curCamera.descriptiveName)
            self.selector.SetBackgroundColour(self.curCamera.color)
            self.Refresh()


    ## Receive a new image and send it to our canvas.
    def onImage(self, data, *args):
        self.canvas.setImage(data)


    ## Return True if we currently display a camera.
    def getIsEnabled(self):
        return self.curCamera is not None


    ## Get the black- and white-point for the view.
    def getScaling(self):
        return self.canvas.getScaling()
## Get the black- and white-point for the view.
    def getCurrentScaling(self):
        return self.canvas.getCurrentScaling()


    ## As above, but the relative values used to generate them instead.
    def getRelativeScaling(self):
        return self.canvas.getRelativeScaling()


    ## Get the current pixel data for the view.
    def getPixelData(self):
        return self.canvas.imageData


    ## Debugging: convert to string.
    def __repr__(self):
        descString = ", disabled"
        if self.curCamera is not None:
            descString = "for %s" % self.curCamera.name
        return "<Camera ViewPanel %s>" % descString
