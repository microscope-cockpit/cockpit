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
import gui.guiUtils

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
## Background colour
BACKGROUND = (128, 128, 128)

class Button(wx.StaticText):
    def __init__(self, 
                 tooltip = '', textSize = 12, isBold = True, 
                 leftAction = None, rightAction = None,
                 **kwargs):
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
        self.SetToolTipString(tooltip)
        self.SetBackgroundColour(BACKGROUND)
        # Realign the label using our custom version of the function
        self.SetLabel(self.GetLabel())
        if leftAction:
            self.Bind(wx.EVT_LEFT_UP, lambda event: leftAction(event))
        if rightAction:
            self.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction(event))


    ## Override of normal StaticText SetLabel, to try to vertically
    # align the text.
    def SetLabel(self, text, *args, **kwargs):
        height = self.GetSize()[1]
        font = self.GetFont()
        fontHeight = font.GetPointSize()
        maxLines = min(height / fontHeight, max)
        numLinesUsed = len(text.split("\n"))
        lineBuffer = (maxLines - numLinesUsed) / 2 - 1
        newText = ("\n" * lineBuffer) + text + ("\n" * lineBuffer)
        wx.StaticText.SetLabel(self, newText, *args, **kwargs)


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
    def __init__(self, parent, label, value='', formatStr=None, unitStr=None):
        super(ValueDisplay, self).__init__(wx.HORIZONTAL)
        self.value = value
        label = Label(
                parent=parent, label=(' ' + label.strip(':') + ':'), 
                size=SMALL_SIZE, style=wx.ALIGN_LEFT)
        label.SetFont(SMALL_FONT)
        self.label = label
        self.Add(label)
        self.valDisplay = Label(
                parent=parent, label=str(value),
                size=SMALL_SIZE, style=(wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE))
        self.valDisplay.SetFont(SMALL_FONT)
        self.Add(self.valDisplay)
        self.formatStr = (formatStr or r'%.6s') + (unitStr or '') + ' '


    def Bind(self, *args, **kwargs):
        self.label.Bind(*args, **kwargs)
        self.valDisplay.Bind(*args, **kwargs)


    def Disable(self):
        return self.valDisplay.Disable()


    def Enable(self):
        return self.valDisplay.Enable()


    def updateValue(self, value=None):
        if value is not None:
            if self.value == value:
                return
            self.value = value
        self.valDisplay.SetLabel(self.formatStr % self.value)


class MultilineDisplay(wx.StaticText):
    def __init__(self, *args, **kwargs):
        if 'style' not in kwargs:
            kwargs['style'] = wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE
        if 'numLines' in kwargs:
            n = kwargs.pop('numLines')
            kwargs['size'] = (DEFAULT_SIZE[0], n * DEFAULT_SIZE[1])
        super(MultilineDisplay, self).__init__(*args, **kwargs)
        self.SetFont(SMALL_FONT)


class Menu(wx.Menu):
    def __init__(self, menuItems, menuCallback):
        """Initialise a menu of menuItems that are handled by menuCallback."""
        ## Call wx.Menu.__init__(self)
        super(Menu, self).__init__()
        for i, item in enumerate(menuItems):
            if len(item):
                self.Append(i, item, '')
                wx.EVT_MENU(self, i, lambda event, item=item:menuCallback(item))
            else:
                self.AppendSeparator()

    def show(self, event):
        gui.guiUtils.placeMenuAtMouse(event.GetEventObject(), self)
