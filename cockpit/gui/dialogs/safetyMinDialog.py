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


import cockpit.gui.guiUtils
import cockpit.interfaces.stageMover

import wx

## @package safetyMinDialog.py
# This package contains the SafetyMin_Dialog class and associated constants and
# functions.

## Altitude for slides.
SLIDE_SAFETY = 7300
## Altitude for dishes.
DISH_SAFETY = 5725


## This class provides a simple wrapper around the interfaces.stageMover's
# safety functionality.
# Note that unlike most
# dialogs, this one does not save the user's settings; instead, it always
# shows the current safety min as the default setting. This is to keep
# users from blindly setting the safety min to what they always use;
# we want them to think about what they're doing.
class SafetyMinDialog(wx.Dialog):
    def __init__(
            self, parent, size = wx.DefaultSize, pos = wx.DefaultPosition, 
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL
            ):
        super().__init__(parent, -1, "Set Z motion minimum", pos, size, style)
        
        self.mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.mainSizer.Add(wx.StaticText(self, -1, 
                "Set the minimum altitude the stage is allowed\n" + 
                "to move to."),
                0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        self.minStageZ = cockpit.gui.guiUtils.addLabeledInput(
                parent = self, sizer = self.mainSizer,
                label = "Stage Z minimum (µm):",
                defaultValue = str(cockpit.interfaces.stageMover.getSoftLimits()[2][0]),
                size = (70, -1), minSize = (150, -1), 
                shouldRightAlignInput = True, border = 3, 
                controlType = wx.TextCtrl)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        slideSafetyButton = wx.Button(self, -1, "Slide")
        slideSafetyButton.SetToolTip(wx.ToolTip("Set the safety to a good value for slide experiments"))
        slideSafetyButton.Bind(wx.EVT_BUTTON, lambda event: self.setSafetyText(SLIDE_SAFETY))
        rowSizer.Add(slideSafetyButton, 0, wx.ALL, 5 )
        dishSafetyButton = wx.Button(self, -1, "Dish")
        dishSafetyButton.SetToolTip(wx.ToolTip("Set the safety to a good value for dish experiments"))
        dishSafetyButton.Bind(wx.EVT_BUTTON, lambda event: self.setSafetyText(DISH_SAFETY))
        rowSizer.Add(dishSafetyButton, 0, wx.ALL, 5)

        self.mainSizer.Add(rowSizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        cancelButton = wx.Button(self, label="Cancel")
        cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, label="Apply")
        startButton.SetToolTip(wx.ToolTip("Apply the chosen safety min"))
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        self.mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(self.mainSizer)
        self.SetAutoLayout(True)
        self.mainSizer.Fit(self)

        startButton.Bind(wx.EVT_BUTTON, self.OnStart)


    ## Set the text for the stage safety min to a default value.
    def setSafetyText(self, value):
        self.minStageZ.SetValue('%.1f' % value)
    

    ## Save the user's selected Z min to the user config, and then set the 
    # new min.
    def OnStart(self, event):
        self.Hide()
        cockpit.interfaces.stageMover.setSoftMin(2, float(self.minStageZ.GetValue()))


## Global dialog singleton.
dialog = None

## Generate the dialog for display. If it already exists, just bring it
# forwards.
def showDialog(parent):
    global dialog
    if dialog:
        try:
            dialog.Show()
            dialog.SetFocus()
            return
        except:
            # dialog got destroyed, so just remake it.
            pass
    dialog = SafetyMinDialog(parent)
    dialog.Show()


