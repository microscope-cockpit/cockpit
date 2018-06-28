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


import wx

## @package cockpit.gui.toggleButton
# This module contains the ToggleButton class and all functions
# associated with that class.

## Color for active controls, barring control-specific colors
ACTIVE_COLOR = (128, 255, 125)
## Color for inactive controls, barring control-specific colors
INACTIVE_COLOR = (128, 128, 128)
## Default size
DEFAULT_SIZE=(120, 48)


## This class provides a simple button that can be toggled on and off, and
# allows you to specify functions to call when it is activated/deactivated.
# It's up to you to handle binding click events and actually
# activating/deactivating it, though.
class ToggleButton(wx.StaticText):
    ## Instantiate the button.
    # \param activeColor Background color when activate() is called
    # \param activeLabel Optional label to switch to when activate() is called
    # \param activateAction Function to call when activate() is called
    # \param inactiveColor As activeColor, but for deactivate()
    # \param inactiveLabel As activeLabel, but for deactivate()
    # \param deactivateAction As activateAction, but for deactivate()
    # \param tooltip Tooltip string to display when moused over
    def __init__(self, 
                 activeColor = ACTIVE_COLOR, inactiveColor = INACTIVE_COLOR, 
                 activateAction = None, deactivateAction = None,
                 activeLabel = None, inactiveLabel = None,
                 tooltip = '', textSize = 12, isBold = True, **kwargs):
        # Default size:
        if 'size' not in kwargs:
            kwargs['size'] = DEFAULT_SIZE
        wx.StaticText.__init__(self,
                style = wx.RAISED_BORDER | wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE,
                **kwargs)
        flag = wx.FONTWEIGHT_BOLD
        if not isBold:
            flag = wx.FONTWEIGHT_NORMAL
        self.SetFont(wx.Font(textSize,wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, flag))
        self.SetToolTip(wx.ToolTip(tooltip))
        self.activeColor = activeColor
        self.inactiveColor = inactiveColor
        self.baseLabel = self.GetLabel()
        self.activeLabel = activeLabel
        self.inactiveLabel = inactiveLabel
        self.activateAction = activateAction
        self.deactivateAction = deactivateAction
        self.SetBackgroundColour(self.inactiveColor)
        self.isActive = False
        # Realign the label using our custom version of the function
        self.SetLabel(self.GetLabel())
        self.Bind(wx.EVT_LEFT_DOWN, lambda event: self.toggle())
        #self.Bind(wx.EVT_RIGHT_DOWN, lambda event: self.toggle())


    ## Override of normal StaticText SetLabel, to try to vertically
    # align the text.
    def SetLabel(self, text, *args, **kwargs):
        height = self.GetSize()[1]
        font = self.GetFont()
        fontHeight = font.GetPointSize()
        maxLines = height / fontHeight
        numLinesUsed = len(text.split("\n"))
        lineBuffer = int((maxLines - numLinesUsed) // 2 - 1)
        newText = ("\n" * lineBuffer) + text + ("\n" * lineBuffer)
        wx.StaticText.SetLabel(self, newText, *args, **kwargs)


    ## Update the button to match known state.
    def updateState(self, isActive):
        if isActive == self.isActive:
            # Do nothing if state is correct.
            return
        self.isActive = isActive
        if isActive:
            color = self.activeColor
            label = self.activeLabel or self.baseLabel
        else:
            color = self.inactiveColor
            label = self.inactiveLabel or self.baseLabel
        self.SetBackgroundColour(color)
        self.SetLabel(label)
        self.Refresh()


    ## Activate or deactivate based on the passed-in boolean
    def setActive(self, shouldActivate, extraText = ''):
        if shouldActivate:
            self.activate(extraText)
        else:
            self.deactivate(extraText)
            

    def activate(self, extraText = ''):
        result = None
        self.isActive = True
        if self.activateAction is not None:
            result = self.activateAction()
        self.SetBackgroundColour(self.activeColor)
        
        label = self.baseLabel
        if self.activeLabel is not None:
            label = self.activeLabel
        if extraText:
            label += '\n' + extraText
        self.SetLabel(label)
        
        self.Refresh()
        return result


    def deactivate(self, extraText = ''):
        result = None
        self.isActive = False
        if self.deactivateAction is not None:
            result = self.deactivateAction()
        self.SetBackgroundColour(self.inactiveColor)
        
        label = self.baseLabel
        if self.inactiveLabel is not None:
            label = self.inactiveLabel
        if extraText:
            label += '\n' + extraText
        self.SetLabel(label)

        self.Refresh()
        return result


    def getIsActive(self):
        return self.isActive


    def toggle(self):
        self.setActive(not self.isActive)


## Enable the specified control, and disable all controls in the given list
# that are not that control.
def activateOneControl(control, listOfControls):
    control.activate()
    for altControl in listOfControls:
        if altControl != control:
            altControl.deactivate()
