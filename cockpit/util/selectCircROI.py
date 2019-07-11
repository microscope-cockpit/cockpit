##This is a window for selecting the ROI for interferometry
# !/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2019 Nick Hall (nicholas.hall@dtc.ox.ac.uk)
# Copyright 2019 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Display a window that allows the user to select a circular area."""

import numpy as np
import wx
from wx.lib.floatcanvas.FloatCanvas import FloatCanvas
import cockpit.util.userConfig as Config

MIN_RADIUS = 8

def normalise(array, scaling = 1):
    minimum = np.min(array)
    maximum = np.max(array)
    norm_array = ((array-minimum)/(maximum-minimum))*scaling
    return norm_array

class ROISelect(wx.Frame):
    def __init__(self, input_image, scale_factor = 1):
        wx.Frame.__init__(self, None, -1, 'ROI selector')
        image_norm = normalise(input_image,scaling=255)
        image_norm_rgb = np.stack((image_norm,)*3,axis=-1)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.img = wx.Image(image_norm_rgb.shape[0],
                            image_norm_rgb.shape[1],
                            image_norm_rgb.astype('uint8'))
        # What, if anything, is being dragged.
        self._dragging = None
        # Canvas
        self.canvas = FloatCanvas(self, size=self.img.GetSize())
        self.canvas.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        self.bitmap = self.canvas.AddBitmap(self.img, (0,0), Position='cc')
        self.circle = self.canvas.AddCircle((0,0), 128, LineColor='cyan', LineWidth=2)
        self.Sizer.Add(self.canvas)
        # Save button
        saveBtn = wx.Button(self, label='Save ROI')
        saveBtn.Bind(wx.EVT_BUTTON, lambda evt, sf=scale_factor: self.onSave(event=evt, sf=sf))
        self.Sizer.Add(saveBtn)
        self.Fit()
        self.Show()

    @property
    def roi(self):
        """Convert circle parameters to ROI x, y and radius"""
        roi_x, roi_y = self.canvas.WorldToPixel(self.circle.XY)
        roi_r = max(self.circle.WH)
        return (roi_x, roi_y, roi_r)

    def onSave(self, event, sf):
        roi_unscaled = np.asarray(self.roi)
        roi = roi_unscaled * sf
        Config.setValue('dm_circleParams', (roi[1], roi[0], roi[2]))
        print("Save ROI button pressed. Current ROI: (%i, %i, %i)" % self.roi)

    def moveCircle(self, pos, r):
        """Set position and radius of circle with bounds checks."""
        x, y = pos
        _x, _y, _r = self.roi
        xmax, ymax = self.img.GetSize()
        if r == _r:
            x_bounded = min(max(r, x), xmax - r)
            y_bounded = min(max(r, y), ymax - r)
            r_bounded = r
        else:
            r_bounded = max(MIN_RADIUS, min(xmax - x, x, ymax - y, y, r))
            x_bounded = min(max(r_bounded, x), xmax - r_bounded)
            y_bounded = min(max(r_bounded, y), ymax - r_bounded)
        self.circle.SetPoint(self.canvas.PixelToWorld( (x_bounded, y_bounded) ))
        self.circle.SetDiameter(2 * r_bounded)
        if any( (x_bounded != x, y_bounded != y, r_bounded != r) ):
            self.circle.SetColor('magenta')
        else:
            self.circle.SetColor('cyan')

    def onMouse(self, event):
        pos = event.GetPosition()
        x, y, r = self.roi
        if event.LeftDClick():
            # Set circle centre
            self.moveCircle(pos, r)
        elif event.Dragging():
            # Drag circle centre or radius
            drag_r = np.sqrt((x - pos[0]) ** 2 + (y - pos[1]) ** 2)
            if self._dragging is None:
                # determine what to drag
                if drag_r < 0.5 * r:
                    # closer to center
                    self._dragging = 'xy'
                else:
                    # closer to edge
                    self._dragging = 'r'
            elif self._dragging is 'r':
                # Drag circle radius
                self.moveCircle((x, y), drag_r)
            elif self._dragging is 'xy':
                # Drag circle centre
                self.moveCircle(pos, r)

        if not event.Dragging():
            # Stop dragging
            self._dragging = None
            self.circle.SetColor('cyan')

        self.canvas.Draw(Force=True)