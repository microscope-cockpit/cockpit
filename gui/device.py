# coding: utf-8
"""gui.device

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================
Class definitions for labels and value displays with default formatting.
"""


import wx

## @package gui.device
# Defines classes for common controls used by cockpit devices.

## Default size
DEFAULT_SIZE = (120, 24)
## Small size
SMALL_SIZE = (60, 18)
## Default font
DEFAULT_FONT = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD)
## Small font
SMALL_FONT = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.NORMAL)


class Label(wx.StaticText):
    """wx.StaticText with some default formatting.
    
    This class does any default formatting, so device classes do not
    have to.
    """
    def __init__(self, *args, **kwargs):
        if 'style' not in kwargs:
            kwargs['style'] = wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE
        if 'size' not in kwargs:
            kwargs['size'] = DEFAULT_SIZE
        super(Label, self).__init__(*args, **kwargs)
        self.SetFont(DEFAULT_FONT)


class ValueDisplay(wx.BoxSizer):
    def __init__(self, parent, label, value, formatStr=None, unitStr=None):
        super(ValueDisplay, self).__init__(wx.HORIZONTAL)
        self.value = value
        label = Label(
                parent=parent, label=(' ' + label.strip(':') + ':'), 
                size=SMALL_SIZE, style=wx.ALIGN_LEFT)
        label.SetFont(SMALL_FONT)
        self.Add(label)
        self.valDisplay = Label(
                parent=parent, label=str(value),
                size=SMALL_SIZE, style=(wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE))
        self.valDisplay.SetFont(SMALL_FONT)
        self.Add(self.valDisplay)
        self.formatStr = (formatStr or r'%.6s') + (unitStr or '') + ' '


    def updateValue(self, value=None):
        if value is not None:
            if self.value == value:
                return
            self.value = value
        self.valDisplay.SetLabel(self.formatStr % self.value)

