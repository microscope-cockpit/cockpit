##This is a window for selecting the ROI for interferometry
# !/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2019 Nick Hall (nicholas.hall@dtc.ox.ac.uk)
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

## Default viewer dimensions.
VIEW_WIDTH, VIEW_HEIGHT = (512, 512)

class ROISelect(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, -1, 'ROI selector')
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.img = wx.Image(VIEW_HEIGHT, VIEW_WIDTH, np.random.randint(0, 255, VIEW_HEIGHT*VIEW_WIDTH))
        # What, if anything, is being dragged.
        self._dragging = None
        # Canvas
        self.canvas = FloatCanvas(self, size=self.img.GetSize())
        self.canvas.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        self.bitmap = self.canvas.AddBitmap(self.img, (0,0), Position='cc')
        self.circle = self.canvas.AddCircle((0,0), 128, LineColor='cyan')
        self.Sizer.Add(self.canvas)
        # Save button
        saveBtn = wx.Button(self, label='Save ROI')
        saveBtn.Bind(wx.EVT_BUTTON, self.onSave)
        self.Sizer.Add(saveBtn)
        self.Fit()
        self.Show()

    @property
    def roi(self):
        """Convert circle parameters to ROI x, y and radius"""
        roi_x, roi_y = self.canvas.WorldToPixel(self.circle.XY)
        roi_r = max(self.circle.WH)
        return (roi_x, roi_y, roi_r)

    def onSave(self, event):
        print("Save ROI button pressed. Current ROI: (%i, %i, %i)" % self.roi)

    def onMouse(self, event):
        pos = event.GetPosition()
        if event.LeftDClick():
            # Set circle centre
            self.circle.SetPoint(self.canvas.PixelToWorld(pos))
        elif event.Dragging():
            # Drag circle centre or radius
            x, y, r = self.roi
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
                self.circle.SetDiameter(2*drag_r)
            elif self._dragging is 'xy':
                # Drag circle centre
                self.circle.SetPoint(self.canvas.PixelToWorld(pos))
        if not event.Dragging():
            # Stop dragging
            self._dragging = None
        self.canvas.Draw(Force=True)


if __name__ == '__main__':
    app = wx.App()
    frame = ROISelect()
    app.MainLoop()
