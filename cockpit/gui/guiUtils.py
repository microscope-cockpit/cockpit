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

import string

import wx
import wx.lib.newevent

## @package cockpit.gui.guiUtils
# This module contains many functions related to the GUI, mostly for setting
# up UI elements and updating various status displays.

# Create a custom event for validation errors.
CockpitValidationErrorEvent, EVT_COCKPIT_VALIDATION_ERROR= wx.lib.newevent.NewCommandEvent()

class _BaseValidator(wx.Validator):
    """Validators for text controls used for numeric entry.

    SomeControl.SetValidator applies a validator via a copy constructor, so
    each derived class has an instance created in this file for passing to
    SetValidator.
    """
    def __init__(self, allowEmpty=False):
        super().__init__()
        self.Bind(wx.EVT_CHAR, self.OnChar)


    def Clone(self):
        # The copy constructor mentioned above.
        return self.__class__()


    def TransferToWindow(self):
        return True


    def TransferFromWindow(self):
        return True


    # Abstract - define in derived calss.
    def _validate(self, value):
        # Test a value. Raise an exception if it is not valid.
        pass


    def Validate(self, parent):
        ctrl = self.GetWindow()
        # Don't validate disabled controls.
        if not (ctrl.Enabled and ctrl.Shown):
            return True

        val = ctrl.GetValue().strip()

        # Validate empty case
        if val == '':
            if getattr(ctrl, 'allowEmpty', False):
                return True
            else:
                evt = CockpitValidationErrorEvent(id=wx.ID_ANY, control=ctrl, empty=True)
                wx.PostEvent(ctrl, evt)
                return False

        # Test with derived class _validate method.
        try:
            self._validate(val)
            return True
        except:
            evt = CockpitValidationErrorEvent(id=wx.ID_ANY, control=ctrl)
            wx.PostEvent(ctrl, evt)
            return False


    def OnChar(self, event):
        # Define in subclass
        pass


class FloatValidator(_BaseValidator):
    """A validator to enforce floating point input.

    * Restricts input to numeric characters an a single decimal point.
    * _validate() tests that string can be parsed as a float.
    """
    def _validate(self, val):
        # Allow special case of single decimal point.
        if val == '.':
            val = '0.'
        return float(val)


    def OnChar(self, event):
        key = event.GetKeyCode()
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            # Pass cursors, backspace, etc. to control
            event.Skip()
        elif chr(key) == '-' and event.EventObject.InsertionPoint == 0:
            event.Skip()
        elif chr(key) in string.digits:
            # Pass any digit to control.
            event.Skip()
        elif chr(key) == '.':
            # Only allow a single '.'
            tc = self.GetWindow()
            val = tc.GetValue()
            selection = event.EventObject.GetStringSelection()
            if '.' not in val or '.' in selection:
                event.Skip()
        return


class IntValidator(_BaseValidator):
    """A validator to enforce floating point input.

    * Restricts input to numeric characters.
    * _validate() tests that string can be parsed as an int."""
    def _validate(self, val):
        return int(val)


    def OnChar(self, event):
        key = event.GetKeyCode()
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            # Pass cursors, backspace, etc. to control
            event.Skip()
        elif chr(key) in string.digits:
            # Pass any digit to control.
            event.Skip()
        return


class CSVValidator(_BaseValidator):
    """A validator to enforce floating point input.

    * Restricts input to numeric characters an a single decimal point.
    * _validate() tests that string can be parsed as a float.
    """
    def _validate(self, val):
        converted = []
        for v in val.split(','):
            converted.append(float(v))
        return converted


    def OnChar(self, event):
        key = event.GetKeyCode()
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            # Pass cursors, backspace, etc. to control
            event.Skip()
        elif chr(key) in string.digits:
            # Pass any digit to control.
            event.Skip()
        elif chr(key) == '-':
            event.Skip()
        elif chr(key) == ',' and len(event.EventObject.Value) > 0:
            # Could also check that adjacent characters are not ','.
            event.Skip()
        elif chr(key) == '.':
            # Could also check that there's only one '.' in the block
            # of text between delimiters.
            event.Skip()
        return

FLOATVALIDATOR = FloatValidator()
INTVALIDATOR = IntValidator()
CSVVALIDATOR = CSVValidator()

## Generate a set of small text boxes for controlling individual lights.
# Return a list of the controls, and the sizer they are contained in.
def makeLightsControls(parent, labels, defaults):
    sizer = wx.FlexGridSizer(2, len(labels), 0, 4)
    controls = []
    for label, defaultVal in zip(labels, defaults):
        sizer.Add(wx.StaticText(parent, -1, label),
                0, wx.ALIGN_RIGHT | wx.ALL, 5)
        # Changed 'control' to 'ctrl' to more clearly discriminate from 'controls'.
        ctrl = wx.TextCtrl(parent, size = (40, -1), name=label)
        ctrl.SetValue(defaultVal)
        # allowEmpty=True lets validator know this control may be empty
        ctrl.SetValidator(FLOATVALIDATOR)
        ctrl.allowEmpty = True
        controls.append(ctrl)
        sizer.Add(ctrl, 0, wx.ALL, 5)
    return controls, sizer



## Show an informative dialog
def showHelpDialog(parent, text):
    wx.MessageDialog(parent, text,
            style = wx.ICON_INFORMATION | wx.OK).ShowModal()


## Add some explanatory text to the given sizer.
def addHelperString(parent, sizer, text, border = 0, flags = wx.ALL):
    label = wx.StaticText(parent, -1, " (What is this?)")
    label.SetForegroundColour((100, 100, 255))
    label.SetToolTip(wx.ToolTip(text))
    sizer.Add(label, 0, flags, border)


## Add a labeled form input to the given sizer. Note that if you pass in
# a wx.CheckBox input, then the input and the explanatory text are swapped.
# @param defaultValue The default value the form input should have.
# @param labelHeightAdjustment Number of pixels to push the input's label down
# by. Sometimes labels and inputs don't align nicely otherwise.
# @param controlType The type of the form input to make. Defaults to 
#        wx.TextCtrl.
# @param control The specific control object to use. Mutually exclusive
#        with the controlType parameter.
# @param helperString Help text to insert, using addHelperString.
# @param flags Any wx flags to use when inserting the object into the sizer.
# \todo The checkbox logic results in substantial code duplication.
def addLabeledInput(parent, sizer, id = -1, label = '',
                    defaultValue = '', size = (-1, -1), minSize = (-1, -1),
                    shouldRightAlignInput = True, border = 0, labelHeightAdjustment = 3,
                    control = None, controlType = None, helperString = '',
                    flags = wx.ALL):
    if control is None:
        if controlType is None:
            controlType = wx.TextCtrl
        control = controlType(parent, id, defaultValue, size = size, name=label)
    text = wx.StaticText(parent, -1, label)
    rowSizer = wx.BoxSizer(wx.HORIZONTAL)
    rowSizer.SetMinSize(minSize)

    if controlType == wx.CheckBox:
        rowSizer.Add(control)
        if shouldRightAlignInput:
            rowSizer.Add((10, -1), 1, wx.EXPAND | wx.ALL, 0)
        rowSizer.Add(text, 0, wx.TOP, labelHeightAdjustment)
        if helperString != '':
            addHelperString(parent, rowSizer, helperString,
                    border = labelHeightAdjustment, flags = wx.TOP)
    else:
        rowSizer.Add(text, 0, wx.TOP, labelHeightAdjustment)
        if helperString != '':
            addHelperString(parent, rowSizer, helperString,
                    border = labelHeightAdjustment, flags = wx.TOP)
        if shouldRightAlignInput:
            # Add an empty to suck up horizontal space
            rowSizer.Add((10, -1), 1, wx.EXPAND | wx.ALL, 0)
        rowSizer.Add(control)
    sizer.Add(rowSizer, 1, flags | wx.EXPAND, border)
    return control


## Simple utility function to pop up the supplied menu at the current 
# mouse location.
def placeMenuAtMouse(frame, menu):
    # Get the Mouse Position on the Screen 
    mousePos = wx.GetMousePosition()
    # Translate the Mouse's Screen Position to the Mouse's Control Position 
    mousePosRelative = frame.ScreenToClient(mousePos)
    frame.PopupMenu(menu, mousePosRelative)


## Pop up a warning dialog, and return the user's reaction.
def getUserPermission(text, title = 'Warning'):
    response = wx.MessageDialog(None, text, title, 
            wx.CANCEL | wx.OK | wx.STAY_ON_TOP | wx.ICON_EXCLAMATION).ShowModal()
    return response == wx.ID_OK


## Given a control, try to parse its value as a number, returning a
# default value on failure.
def tryParseNum(control, convertFunc = int, default = 0):
    try:
        return convertFunc(control.GetValue())
    except:
        return default
