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
import cockpit.gui.imageViewer.viewCanvas

import numpy
import wx


## This UI widget shows a sequence of images.
class ImageSequenceViewer(wx.Frame):
    ## \param images WTZYX array of image data to display.
    # \param title Title string for the window. We'll update it with pixel
    # value information when the user mouses over the display.
    def __init__(self, images, title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.images = images
        self.title = title
        ## Current image/pixel under examination.
        self.curViewIndex = numpy.zeros(5, dtype = numpy.int)

        ## Panel for holding UI widgets.
        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(wx.WHITE)

        # Set up our UI -- just a collection of sliders to change the
        # image we show, plus some keyboard shortcuts.
        ## Maps axes to the Sliders for those axes.
        self.axisToSlider = dict()
        sizer = wx.BoxSizer(wx.VERTICAL)
        sliderSizer = wx.BoxSizer(wx.HORIZONTAL)
        for i, label in enumerate(['Wavelength', 'Time', 'Z']):
            if self.images.shape[i] > 1:
                # We need a slider for this dimension.
                sliderSizer.Add(self.makeSlider(i, label))
        sizer.Add(sliderSizer)

        self.canvas = cockpit.gui.imageViewer.viewCanvas.ViewCanvas(self.panel,
                size = (self.images.shape[-1], self.images.shape[-2] + 40) )
        sizer.Add(self.canvas)
        self.panel.SetSizerAndFit(sizer)
        temp = wx.BoxSizer(wx.VERTICAL)
        temp.Add(self.panel)
        self.SetSizerAndFit(temp)
        self.Show()
        # For some reason, if we don't do this, then the first time we try
        # to access curViewIndex in self.setCurImage we get strange values.
        self.setCurImage()

        events.subscribe('image pixel info', self.onImagePixelInfo)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        accelTable = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_MULTIPLY, 1), 
            (wx.ACCEL_NORMAL, wx.WXK_LEFT, 2),
            (wx.ACCEL_NORMAL, wx.WXK_RIGHT, 3),
            (wx.ACCEL_NORMAL, wx.WXK_UP, 4),
            (wx.ACCEL_NORMAL, wx.WXK_DOWN, 5)])
        self.SetAcceleratorTable(accelTable)
        self.Bind(wx.EVT_MENU,  self.onRescale, id= 1)
        for id, delta in [(2, (0, -1)), (3, (0, 1)), (4, (-1, 0)), (5, (1, 0))]:
            self.Bind(wx.EVT_MENU,  lambda event, delta = delta: self.shiftView(delta), id= id)


    ## Unsubscribe from the pixel info event so we don't leave stale functions
    # lying around.
    def onClose(self, event):
        events.unsubscribe('image pixel info', self.onImagePixelInfo)
        event.Skip()


    ## Update our title bar with the pixel brightness info.
    def onImagePixelInfo(self, coords, value):
        self.SetTitle("%s: (%d, %d): %.2f" % (self.title, coords[0], coords[1], value))


    ## Rescale the view.
    def onRescale(self, event = None):
        self.canvas.resetPixelScale()


    ## Given a (time, Z) delta, adjust the current view index by that delta.
    def shiftView(self, delta):
        for i, val in enumerate(delta):
            axis = i + 1
            target = self.curViewIndex[axis] + delta[i]
            self.curViewIndex[axis] = max(0, min(self.images.shape[axis]  - 1, target))
            if axis in self.axisToSlider:
                self.axisToSlider[axis].SetValue(self.curViewIndex[axis])
        self.setCurImage()


    ## Generate a slider for changing the view along the specified axis.
    def makeSlider(self, axis, label):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self.panel, -1, label, style = wx.ALIGN_CENTRE),
                1, wx.ALL | wx.EXPAND, 5)
        slider = wx.Slider(self.panel, maxValue = self.images.shape[axis] - 1,
                style = wx.SL_AUTOTICKS | wx.SL_LABELS)
        slider.Bind(wx.EVT_SCROLL, lambda event: self.onSlider(axis, event))
        self.axisToSlider[axis] = slider
        sizer.Add(slider)
        return sizer


    ## Handle a slider moving.
    def onSlider(self, axis, event):
        position = event.GetPosition()
        self.curViewIndex[axis] = position
        self.setCurImage()
        

    ## Set the current image, per our current view index.
    def setCurImage(self):
        curImage = self.images[tuple(self.curViewIndex[:3])]
        self.canvas.setImage(curImage)

