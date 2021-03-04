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

import cockpit.gui.guiUtils
import cockpit.interfaces.stageMover
import cockpit.util.userConfig

import wx
import numpy


## This class shows a simple dialog to the user that allows them to lay down
# a grid of sites on the mosaic. They can then use this to image large areas
# in a regulated manner without relying on the mosaic's spiral system. 
class GridSitesDialog(wx.Dialog):
    ## Create the dialog, and lay out its UI widgets. 
    def __init__(self, parent):
        super().__init__(parent, -1, "Place a Grid of Sites")

        ## Config-loaded settings for the form.
        self.settings = cockpit.util.userConfig.getValue('gridSitesDialog', default = {
                'numRows' : '10',
                'numColumns' : '10',
                'imageWidth' : '512',
                'imageHeight' : '512',
                'markerSize': '25',
            }
        )
        
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1,
                "The upper-left corner of the grid will be at the current " +
                "stage position.")
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        self.numRows = cockpit.gui.guiUtils.addLabeledInput(self, sizer,
                label = "Number of rows:",
                defaultValue = self.settings['numRows'])
        self.numColumns = cockpit.gui.guiUtils.addLabeledInput(self, sizer,
                label = "Number of columns:",
                defaultValue = self.settings['numColumns'])
        self.imageWidth = cockpit.gui.guiUtils.addLabeledInput(self, sizer,
                label = "Horizontal spacing (pixels):",
                defaultValue = self.settings['imageWidth'])
        self.imageHeight = cockpit.gui.guiUtils.addLabeledInput(self, sizer,
                label = "Vertical spacing (pixels):",
                defaultValue = self.settings['imageHeight'])
        self.markerSize = cockpit.gui.guiUtils.addLabeledInput(self, sizer,
                label = "Marker size (default 25):",
                defaultValue = self.settings['markerSize'])
        
        buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancelButton.SetToolTipString("Close this window")
        buttonBox.Add(cancelButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Mark sites")
        buttonBox.Add(startButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        buttonBox.Add((20, -1), 1, wx.ALL, 5)
        sizer.Add(buttonBox, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.Bind(wx.EVT_BUTTON, self.OnStart, startButton)


    ## Create the grid of sites. 
    def OnStart(self, evt):
        self.saveSettings()

        curLoc = cockpit.interfaces.stageMover.getPosition()
        imageWidth = float(self.imageWidth.GetValue())
        imageHeight = float(self.imageHeight.GetValue())
        markerSize = float(self.markerSize.GetValue())
        pixelSize = wx.GetApp().Objectives.GetPixelSize()

        for xOffset in range(int(self.numColumns.GetValue())):
            xLoc = curLoc[0] - xOffset * pixelSize * imageWidth
            for yOffset in range(int(self.numRows.GetValue())):
                yLoc = curLoc[1] - yOffset * pixelSize * imageHeight
                target = numpy.array([xLoc, yLoc, curLoc[2]])
                newSite = cockpit.interfaces.stageMover.Site(target, size = markerSize)
                cockpit.interfaces.stageMover.saveSite(newSite)
        self.Destroy()


    ## Save the user's settings to the configuration file.
    def saveSettings(self):
        cockpit.util.userConfig.setValue('gridSitesDialog', {
                'numRows': self.numRows.GetValue(),
                'numColumns': self.numColumns.GetValue(),
                'imageWidth': self.imageWidth.GetValue(),
                'imageHeight': self.imageHeight.GetValue(),
                'markerSize': self.markerSize.GetValue(),
            }
        )
        

## Show the dialog.
def showDialog(parent):
    dialog = GridSitesDialog(parent)
    dialog.Show()
    dialog.SetFocus()
    return dialog
