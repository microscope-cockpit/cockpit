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


"""gui.device

Class definitions for labels and value displays with default formatting.
"""

import sys

from collections import OrderedDict
import wx
import wx.propgrid
import cockpit.gui.guiUtils
from cockpit.handlers.deviceHandler import STATES
import cockpit.util.userConfig
import cockpit.util.threads
from cockpit import events
from cockpit.events import DEVICE_STATUS
from cockpit.gui import EvtEmitter, EVT_COCKPIT


## @package cockpit.gui.device
# Defines classes for common controls used by cockpit devices.

## Default size
DEFAULT_SIZE = (120, 24)
## Small size
SMALL_SIZE = (60, 18)
## Background colour
BACKGROUND = (128, 128, 128)


class Button(wx.StaticText):
    """A generic button for devices."""
    def __init__(self,
                 tooltip = '', textSize = 12, isBold = True,
                 leftAction = None, rightAction = None,
                 **kwargs):
        # Default size:
        if 'size' not in kwargs:
            kwargs['size'] = DEFAULT_SIZE
        super().__init__(style = wx.RAISED_BORDER | wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE,
                         **kwargs)
        if isBold:
            self.SetFont(self.GetFont().Bold())
        self.SetToolTip(wx.ToolTip(tooltip))
        self.SetBackgroundColour(BACKGROUND)
        # Realign the label using our custom version of the function
        self.SetLabel(self.GetLabel())
        if leftAction:
            self.Bind(wx.EVT_LEFT_UP, lambda event: leftAction(event))
        if rightAction:
            self.Bind(wx.EVT_RIGHT_UP, lambda event: rightAction(event))
            # This control has a special right-click behaviour, so don't pass
            # up EVT_CONTEXT_MENU CommandEvents.
            self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)


    def update(self, value=None):
        """Update the label.

        self.value may be a function or a string."""
        if value is not None:
            self.value = value
        if callable(self.value):
            self.SetLabel(self.value())
        else:
            self.SetLabel(self.value)


    ## Override of normal StaticText SetLabel, to try to vertically
    # align the text.
    def SetLabel(self, text, *args, **kwargs):
        height = self.GetSize()[1]
        font = self.GetFont()
        fontHeight = font.GetPointSize()
        maxLines = height // fontHeight
        numLinesUsed = len(text.split("\n"))
        lineBuffer = (maxLines - numLinesUsed) // 2 - 1
        newText = ("\n" * lineBuffer) + text + ("\n" * lineBuffer)
        super().SetLabel(newText, *args, **kwargs)


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
        super().__init__(*args, **kwargs)
        self.SetFont(self.GetFont().Bold())


class ValueDisplay(wx.BoxSizer):
    """A simple value display for devices."""
    def __init__(self, parent, label, value='', formatStr=None, unitStr=None):
        super().__init__(wx.HORIZONTAL)
        self.value = value
        label = Label(
            parent=parent, label=(' ' + label.strip(':') + ':'),
            size=SMALL_SIZE, style=wx.ALIGN_LEFT)
        label.SetFont(label.GetFont().Smaller())
        self.label = label
        self.Add(label)
        self.valDisplay = Label(
            parent=parent, label=str(value),
            size=SMALL_SIZE, style=(wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE))
        self.valDisplay.SetFont(self.valDisplay.GetFont().Smaller())
        self.Add(self.valDisplay)
        self.formatStr = (formatStr or r'%.6s') + (unitStr or '') + ' '


    def Bind(self, *args, **kwargs):
        self.label.Bind(*args, **kwargs)
        self.valDisplay.Bind(*args, **kwargs)


    def Disable(self):
        return self.valDisplay.Disable()


    def Enable(self):
        return self.valDisplay.Enable()


    def update(self, value=None):
        """Update the displayed value.

        self.value may be a function or a string."""
        if value is not None:
            self.value = value
        if callable(self.value):
            self.valDisplay.SetLabel(self.formatStr % self.value())
        else:
            self.valDisplay.SetLabel(self.formatStr % self.value)


class MultilineDisplay(wx.StaticText):
    """A multi-line display for devices."""
    def __init__(self, *args, **kwargs):
        if 'style' not in kwargs:
            kwargs['style'] = wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE
        if 'numLines' in kwargs:
            n = kwargs.pop('numLines')
            kwargs['size'] = (DEFAULT_SIZE[0], n * DEFAULT_SIZE[1])
        super().__init__(*args, **kwargs)
        self.SetFont(self.GetFont().Smaller())


class Menu(wx.Menu):
    def __init__(self, menuItems, menuCallback):
        """Initialise a menu of menuItems that are handled by menuCallback."""
        super().__init__()
        for i, item in enumerate(menuItems):
            if len(item):
                self.Append(i, item, '')
                self.Bind(wx.EVT_MENU,  lambda event, index=i, item=item:menuCallback(index, item), id= i)
            else:
                self.AppendSeparator()

    def show(self, event):
        cockpit.gui.guiUtils.placeMenuAtMouse(event.GetEventObject(), self)


class EnumChoice(wx.Choice):
    """A wx.Choice which coverts between it's own 0-based indexes and enum values."""
    def __init__(self, *args, **kwargs):
        self._enumitems = []
        self._action = None
        super().__init__(*args, **kwargs)

    def Set(self, items):
        """Store the enum values in a 0-indexed list for recall later."""
        self._enumitems = [value for value, desc in items]
        super().Set([desc for value, desc in items])

    def _onChoice(self, evt):
        self._action(self._enumitems[evt.Selection])

    def setOnChoice(self, action):
        self._action = action
        self.Bind(wx.EVT_CHOICE, self._onChoice)


_BMP_SIZE=(16,16)

_BMP_OFF = wx.Bitmap.FromRGBA(*_BMP_SIZE, red=0, green=32, blue=0,
                             alpha=wx.ALPHA_OPAQUE)
_BMP_ON = wx.Bitmap.FromRGBA(*_BMP_SIZE, red=0, green=255, blue=0,
                             alpha=wx.ALPHA_OPAQUE)
_BMP_WAIT = wx.Bitmap.FromRGBA(*_BMP_SIZE, red=255, green=165, blue=0,
                              alpha=wx.ALPHA_OPAQUE)
_BMP_ERR = wx.Bitmap.FromRGBA(*_BMP_SIZE, red=255, green=0, blue=0,
                             alpha=wx.ALPHA_OPAQUE)

_BMPS = {STATES.enabling: _BMP_WAIT,
         STATES.busy: _BMP_WAIT,
         STATES.enabled: _BMP_ON,
         STATES.disabled: _BMP_OFF,
         STATES.error: _BMP_ERR,
         None: _BMP_ERR}

class EnableButton(wx.ToggleButton):
    def __init__(self, parent, deviceHandler):
        super().__init__(parent, wx.ID_ANY, deviceHandler.name)
        self.device = deviceHandler
        # Devices should update bitmap on startup, but reserve bitmap
        # space for those that do not yet do so.
        self.SetBitmap(_BMP_OFF, wx.RIGHT)
        listener = EvtEmitter(self, DEVICE_STATUS)
        listener.Bind(EVT_COCKPIT, self.onStatusEvent)
        self.Bind(wx.EVT_TOGGLEBUTTON, deviceHandler.toggleState)
        self.state = None
        self.others = [] # A list of controls that should be en/disabled accordingly.


    def manageStateOf(self, others):
        try:
            self.others.extend(others)
        except:
            # others is not iterable
            self.others.append(others)


    @cockpit.util.threads.callInMainThread
    def setState(self, state):
        if self.state == state:
            return
        # GTK only needs SetBitmap, but MSW needs *all* bitmaps updating.
        self.SetBitmap(_BMPS[state], wx.RIGHT)
        self.SetBitmapCurrent(_BMPS[state])
        self.SetBitmapFocus(_BMPS[state])
        self.SetBitmapPressed(_BMPS[state])
        self.SetBitmapDisabled(_BMPS[state])
        self.state = state
        if state == STATES.enabling:
            self.Disable()
        else:
            self.Enable()
        if state == STATES.enabled:
            for o in self.others: o.Enable()
        else:
            for o in self.others: o.Disable()
        # Ensure button is in pressed state if device is enabled, because
        # other controls or events may cause a state change.
        self.SetValue(state == STATES.enabled)
        # Enabling/disabling control sets focus to None. Set it to parent so keypresses still handled.
        wx.CallAfter(self.Parent.SetFocus)


    def onStatusEvent(self, evt):
        device, state = evt.EventData
        if device != self.device:
            return
        self.setState(state)


class TupleOfIntsProperty(wx.propgrid.StringProperty):
    def __init__(self, *args, **kwargs):
        if 'value' in kwargs:
            kwargs['value'] = ", ".join([str(v) for v in kwargs['value']])
        super().__init__(*args, **kwargs)


    def SetValue(self, value, **kwargs):
        value = ", ".join([str(v) for v in value])
        super().SetValue(value, **kwargs)


    def GetValue(self):
        return tuple([int(v) for v in self.m_value.split(",")])


class SettingsEditor(wx.Frame):
    _SETTINGS_TO_PROPTYPES = {'int': wx.propgrid.IntProperty,
                             'float': wx.propgrid.FloatProperty,
                             'bool': wx.propgrid.BoolProperty,
                             'enum': wx.propgrid.EnumProperty,
                             'str': wx.propgrid.StringProperty,
                             'tuple': TupleOfIntsProperty,
                             str(int): wx.propgrid.IntProperty,
                             str(float): wx.propgrid.FloatProperty,
                             str(bool): wx.propgrid.BoolProperty,
                             str(str): wx.propgrid.StringProperty,
                             str(tuple): TupleOfIntsProperty}


    def __init__(self, device, parent=None, handler=None):
        super().__init__(parent, wx.ID_ANY, style=wx.FRAME_FLOAT_ON_PARENT)
        self.device = device
        self.SetTitle("%s settings" % device.name)
        self.settings = {}
        self.current = {}
        self.handler = handler
        #self.handler.addListener(self)
        #self.panel = wx.Panel(self, wx.ID_ANY, style=wx.WANTS_CHARS)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.grid = wx.propgrid.PropertyGrid(self,
                                             style=wx.propgrid.PG_SPLITTER_AUTO_CENTER)
        self.grid.SetColumnProportion(0, 2)
        self.grid.SetColumnProportion(1, 1)
        self.populateGrid()
        self.Bind(wx.propgrid.EVT_PG_CHANGED, self.onPropertyChange)
        sizer.Add(self.grid, 1, wx.EXPAND | wx.ALIGN_LEFT | wx.ALIGN_TOP)

        sizer.AddSpacer(2)
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        #saveButton = wx.Button(self, id=wx.ID_SAVE)
        #saveButton.SetToolTip(wx.ToolTip("Save current settings as defaults."))
        #saveButton.Bind(wx.EVT_BUTTON, self.onSave)
        #buttonSizer.Add(saveButton, 0, wx.ALIGN_RIGHT, 0, 0)

        okButton = wx.Button(self, id=wx.ID_OK)
        okButton.Bind(wx.EVT_BUTTON, self.onClose)
        okButton.SetToolTip(wx.ToolTip("Apply settings and close this window."))
        buttonSizer.Add(okButton, 0)

        cancelButton = wx.Button(self, id=wx.ID_CANCEL)
        cancelButton.Bind(wx.EVT_BUTTON, self.onClose)
        cancelButton.SetToolTip(wx.ToolTip("Close this window without applying settings."))
        buttonSizer.Add(cancelButton, 0)

        applyButton = wx.Button(self, id=wx.ID_APPLY)
        applyButton.SetToolTip(wx.ToolTip("Apply these settings."))
        applyButton.Bind(wx.EVT_BUTTON, lambda evt: self.device.updateSettings(self.current))
        buttonSizer.Add(applyButton, 0)

        sizer.Add(buttonSizer, 0, wx.ALIGN_CENTER, 0, 0)
        self.SetSizerAndFit(sizer)
        self.SetMinSize((256, -1))
        events.subscribe(events.SETTINGS_CHANGED % self.device, self.updateGrid)
        self.Bind(wx.EVT_SHOW, lambda evt: self.updateGrid())


    def onClose(self, evt):
        events.unsubscribe(events.SETTINGS_CHANGED % self.device, self.updateGrid)
        if evt.GetId() == wx.ID_OK:
            self.device.updateSettings(self.current)
        self.Close()
        # Do stuff to update local device state.

    def onPropertyChange(self, event):
        prop = event.GetProperty()
        name = event.GetPropertyName()
        setting = self.settings[name]
        # Fetch and validate the value from the control - using event.GetValue
        # may return the wrong type for custom properties.
        value = prop.GetValue()

        if setting['type'] in (str(int), str(float), 'int', 'float'):
            # Bound to min/max.
            lims = setting['values']
            value = sorted(tuple(lims) + (value,))[1]
        elif setting['type'] in (str(str), 'str'):
            # Limit string length.
            value = value[0, setting['values']]

        self.current[name] = value
        if value != self.device.settings[name]:
            prop.SetTextColour(wx.Colour(255, 0, 0))
        else:
            prop.SetTextColour(wx.Colour(0, 0, 0))
        self.grid.SelectProperty(prop)


    def onSave(self, event):
        if self.handler is None:
            return
        settings = self.grid.GetPropertyValues()
        for name, value in settings.items():
            if self.settings[name]['type'] == 'enum':
                settings[name] = self.settings[name]['values'][value]
        cockpit.util.userConfig.setValue(self.handler.getIdentifier() + '_SETTINGS',
                            settings)


    def updateGrid(self):
        """Update property state and values.

        Note: grid.SetValues does not work for custom property classes -
        it seems that it calls the C++ SetValue on the base class rather
        than the python SetValue on the derived class."""
        if not self.IsShown():
            return
        self.Freeze()
        grid = self.grid
        self.settings = OrderedDict(self.device.describe_settings())
        if self.current:
            self.current.update(self.device.settings)
        else:
            self.current = self.device.get_all_settings()
        # Enable/disable controls, and update Choices for enums.
        for prop in grid.Properties:
            prop.SetTextColour(wx.Colour(0, 0, 0))
            name = prop.GetName()
            desc = self.settings[name]
            if desc['type'] in ('enum'):
                indices, items = zip(*desc['values'])
                labels = [str(i) for i in items]
                choices = wx.propgrid.PGChoices(labels, indices)
                prop.SetChoices(choices)
                if self.current[name] not in indices:
                    # Indicate a problem with this item.
                    prop.SetTextColour('red')
            try:
                prop.Enable(not self.settings[name]['readonly'])
            except wx._core.PyAssertionError:
                # Bug in wx in stc.EnsureCaretVisible, could not convert to a long.
                pass
            try:
                prop.SetValue(self.current[name])
                prop.SetTextColour('black')
            except:
                prop.SetTextColour('red')
        self.Thaw()


    def populateGrid(self):
        """Create the propertgrid controls.

        We just create the controls here - their values will be updated
        by updateGrid."""
        grid = self.grid
        self.settings = OrderedDict(self.device.describe_settings())
        for key, desc in self.settings.items():
            propType = SettingsEditor._SETTINGS_TO_PROPTYPES.get(desc['type'])
            if propType is wx.propgrid.IntProperty:
                # Use a float if integer may exceed IntProperty representation.
                # The representation is dependent on whether or not  wx was compiled
                # with wxUSE_LONG_LONG defined. I can't find a way to easily figure
                # this out from python, so we go for the safer limit.
                # Read-only ints may have a desc['values'] of (None, None), so avoid
                # the max() comparison in that case.
                if None in desc['values'] or max(desc['values']) > wx.INT32_MAX:
                    propType = wx.propgrid.FloatProperty
            try:
                prop = propType(label=key, name=key)
            except Exception as e:
                sys.stderr.write("populateGrid threw exception for key %s with value %s: %s"
                                 % (key, value, e))
            if desc['readonly']:
                prop.Enable(False)
            grid.Append(prop)
