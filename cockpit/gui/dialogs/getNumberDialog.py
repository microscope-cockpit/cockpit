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

import wx


## This class allows for prompting the user for a number, similar to
# wx.GetNumberFromUser except that we allow for floating point values as well.
class GetNumberDialog(wx.Dialog):
    def __init__(self, parent, title, prompt, default, atMouse=False):
        # Nothing checks how the window was closed, so the OK button should
        # be the only way to close it.
        style = wx.CAPTION
        if atMouse:
            mousePos = wx.GetMousePosition()
            super().__init__(parent, -1, title, mousePos, style=style)
        else:
            super().__init__(parent, -1, title, style=style)
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.value = cockpit.gui.guiUtils.addLabeledInput(
                parent = self, sizer = mainSizer,
                label = prompt,
                defaultValue = str(default),
                size = (70, -1), minSize = (150, -1), 
                shouldRightAlignInput = True, border = 3, 
                controlType = wx.TextCtrl)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        #cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        #cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        #buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Okay")
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(mainSizer)
        self.SetAutoLayout(True)
        mainSizer.Fit(self)


    def getValue(self):
        return self.value.GetValue()



## As above, but we can accept any number of prompts for multiple numbers.
class GetManyNumbersDialog(wx.Dialog):
    def __init__(self, parent, title, prompts, defaultValues, atMouse=False):
        # Nothing checks how the window was closed, so the OK button should
        # be the only way to close it.
        style = wx.CAPTION
        if atMouse:
            mousePos = wx.GetMousePosition()
            super().__init__(parent, -1, title, mousePos, style=style)
        else:
            super().__init__(parent, -1, title, style=style)
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.controls = []
        for i, prompt in enumerate(prompts):
            control = cockpit.gui.guiUtils.addLabeledInput(
                    parent = self, sizer = mainSizer,
                    label = prompt,
                    defaultValue = str(defaultValues[i]),
                    size = (70, -1), minSize = (150, -1), 
                    shouldRightAlignInput = True, border = 3, 
                    controlType = wx.TextCtrl)
            self.controls.append(control)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        #cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        #cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        #buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Okay")
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(mainSizer)
        self.SetAutoLayout(True)
        mainSizer.Fit(self)


    def getValues(self):
        return [control.GetValue() for control in self.controls]


        
def getNumberFromUser(parent, title, prompt, default, atMouse=True):
    dialog = GetNumberDialog(parent, title, prompt, default, atMouse)
    dialog.ShowModal()
    return dialog.getValue()
    

def getManyNumbersFromUser(parent, title, prompts, defaultValues, atMouse=True):
    dialog = GetManyNumbersDialog(parent, title, prompts, defaultValues, atMouse)
    dialog.ShowModal()
    return dialog.getValues()
