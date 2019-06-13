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

## Default viewer dimensions.
(VIEW_WIDTH, VIEW_HEIGHT) = (512, 512)

class ROISelect(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, -1, 'ROI selector')

        self.panel = wx.Panel(self)
        self.PhotoMaxSize = 512
        img_np = np.random.randint(0, 255, (VIEW_HEIGHT, VIEW_WIDTH))
        self.img = wx.Image(VIEW_HEIGHT, VIEW_WIDTH, img_np)

        # Current mouse position
        self.curMouseX = self.curMouseY = None
        self.roi_x = self.roi_y = self.roi_radius = None

        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.createWidgets()
        self.Show()

    def createWidgets(self):
        instructions = 'Select the region of interest'
        self.mainSizer = wx.BoxSizer(wx.VERTICAL)

        instructLbl = wx.StaticText(self.panel, label=instructions)
        self.mainSizer.Add(instructLbl, 0, wx.ALL, 5)

        self.imageCtrl = wx.StaticBitmap(self.panel, wx.ID_ANY,
                                         wx.Bitmap(self.img))
        self.imageCtrl.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        self.imageCtrl.Bind(wx.EVT_PAINT, self.drawCircle)
        self.mainSizer.Add(self.imageCtrl, 0, wx.ALL, 5)

        saveBtn = wx.Button(self.panel, label='Save ROI')
        saveBtn.Bind(wx.EVT_BUTTON, self.onSave)
        self.mainSizer.Add(saveBtn, 0, wx.ALL, 5)

        self.panel.SetSizer(self.mainSizer)
        self.mainSizer.Fit(self)

        self.panel.Layout()

    def onSave(self, event):
        print("Save ROI button pressed. Current ROI: (%i, %i, %i)" %(
            self.roi_x,
            self.roi_y,
            self.roi_radius
        ))

    def onMouse(self, event):
        self.curMouseX, self.curMouseY = event.GetPosition()
        if event.LeftDClick():
            self.roi_x = self.curMouseX
            self.roi_y = self.curMouseY
            print("Current mouse position (click): X = %i Y = %i" %(self.curMouseX, self.curMouseY))
        elif event.LeftIsDown():
            try:
                self.roi_radius = np.sqrt((abs(self.roi_x - self.curMouseX))**2
                                      + (abs(self.roi_y - self.curMouseY))**2)
                print("Current mouse position (dragging): X = %i Y = %i" % (self.curMouseX, self.curMouseY))
            except:
                print("No ROI centre selected")
        elif event.RightIsDown():
            self.roi_x = self.curMouseX
            self.roi_y = self.curMouseY
            print("Current mouse position (right): X = %i Y = %i" % (self.curMouseX, self.curMouseY))
        else:
            return

    def onPaint(self, event):
        print("In onPaint")
        dc = wx.PaintDC(self)

    def drawCircle(self, event):
        print("In drawCirle")
        if self.imageCtrl:
            dc = wx.PaintDC(self.imageCtrl)

            dc.DrawBitmap(wx.Bitmap(self.img), 0, 0)

            if self.roi_radius is not None:
                dc.SetBrush(wx.Brush('red'))
                dc.DrawCircle(self.roi_x, self.roi_y, self.roi_radius)
        else:
            print("imageCtrl doesn't exists")


if __name__ == '__main__':
    app = wx.App()
    frame = ROISelect()
    app.MainLoop()
