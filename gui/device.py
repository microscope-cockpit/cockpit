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


from collections import OrderedDict
import wx
import wx.propgrid
import gui.guiUtils
from handlers.deviceHandler import STATES
from toggleButton import ACTIVE_COLOR, INACTIVE_COLOR
from util import userConfig
import gui.loggingWindow as log
import events

## @package gui.device
# Defines classes for common controls used by cockpit devices.

## Default size
DEFAULT_SIZE = (120, 24)
## Small size
SMALL_SIZE = (60, 18)
## Tall size
TALL_SIZE = (DEFAULT_SIZE[0], 64)
## Default font
DEFAULT_FONT = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD)
## Small font
SMALL_FONT = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
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
    """A simple value display for devices."""
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
        super(MultilineDisplay, self).__init__(*args, **kwargs)
        self.SetFont(SMALL_FONT)


class Menu(wx.Menu):
    def __init__(self, menuItems, menuCallback):
        """Initialise a menu of menuItems that are handled by menuCallback."""
        super(Menu, self).__init__()
        for i, item in enumerate(menuItems):
            if len(item):
                self.Append(i, item, '')
                wx.EVT_MENU(self, i, lambda event, index=i, item=item:menuCallback(index, item))
            else:
                self.AppendSeparator()

    def show(self, event):
        gui.guiUtils.placeMenuAtMouse(event.GetEventObject(), self)


class EnableButton(Button):
    """A button to enable/disable devices."""
    def enable(self, which):
        if which is False:
            self.Disable()
            self.SetEvtHandlerEnabled(False)
        else:
            self.Enable()
            self.SetEvtHandlerEnabled(True)


    def onEnabledEvent(self, state):
        if state is STATES.enabled:
            self.enable(True)
            self.SetLabel("ON")
            self.SetBackgroundColour(ACTIVE_COLOR)
        elif state is STATES.disabled:
            self.enable(True)
            self.SetLabel("OFF")
            self.SetBackgroundColour(INACTIVE_COLOR)
        elif state is STATES.enabling:
            self.enable(False)
        elif state is STATES.error:
            self.SetBackgroundColour((255, 0, 0))
            self.enable(True)
            self.SetLabel("ERROR")
        self.Refresh()



class SettingsEditor(wx.Frame):
    _SETTINGS_TO_PROPTYPES = {'int': wx.propgrid.IntProperty,
                             'float': wx.propgrid.FloatProperty,
                             'bool': wx.propgrid.BoolProperty,
                             'enum': wx.propgrid.EnumProperty,
                             'str': wx.propgrid.StringProperty,
                             str(int): wx.propgrid.IntProperty,
                             str(float): wx.propgrid.FloatProperty,
                             str(bool): wx.propgrid.BoolProperty,
                             str(str): wx.propgrid.StringProperty, }


    def __init__(self, device, handler=None):
        wx.Frame.__init__(self, None, wx.ID_ANY, style=wx.DEFAULT_FRAME_STYLE & ~wx.CLOSE_BOX)
        self.device = device
        self.SetTitle("Settings for %s." % device.name)
        self.settings = None
        self.handler = handler
        self.handler.addListener(self)
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
        #saveButton.SetToolTipString("Save current settings as defaults.")
        #saveButton.Bind(wx.EVT_BUTTON, self.onSave)
        #buttonSizer.Add(saveButton, 0, wx.ALIGN_RIGHT, 0, 0)

        okButton = wx.Button(self, id=wx.ID_OK)
        okButton.Bind(wx.EVT_BUTTON, self.onClose)
        okButton.SetToolTipString("Apply settings and close this window.")
        buttonSizer.Add(okButton, 0, wx.ALIGN_RIGHT)

        cancelButton = wx.Button(self, id=wx.ID_CANCEL)
        cancelButton.Bind(wx.EVT_BUTTON, self.onClose)
        cancelButton.SetToolTipString("Close this window without applying settings.")
        buttonSizer.Add(cancelButton, 0, wx.ALIGN_RIGHT)

        applyButton = wx.Button(self, id=wx.ID_APPLY)
        applyButton.SetToolTipString("Apply these settings.")
        applyButton.Bind(wx.EVT_BUTTON, lambda evt: self.device.updateSettings(self.current))
        buttonSizer.Add(applyButton, 0, wx.ALIGN_RIGHT)

        sizer.Add(buttonSizer, 0, wx.ALIGN_CENTER, 0, 0)
        self.SetSizerAndFit(sizer)
        self.SetMinSize((256, -1))
        #self.SetMaxSize((self.GetMinWidth(), -1))
        events.subscribe("%s settings changed" % self.device, self.updateGrid)


    def onEnabledEvent(self, evt):
        if self.IsShown():
            self.updateGrid()


    def onClose(self, evt):
        events.unsubscribe("%s settings changed" % self.device, self.updateGrid)
        if evt.GetId() == wx.ID_OK:
            self.device.updateSettings(self.current)
        self.Close()
        # Do stuff to update local device state.

    def onPropertyChange(self, event):
        prop = event.GetProperty()
        name = event.GetPropertyName()
        setting = self.settings[name]
        # Fetch and validate the value.
        if prop.ClassName == 'wxEnumProperty':
            index = event.GetPropertyValue()
            # Look up value as the original type, not as str from the wxProperty.
            # setting['values'] only contains allowed values, so this also
            # serves as validation for enums.
            value = setting['values'][index]
        elif setting['type'] in (str(int), str(float), 'int', 'float'):
            value = event.GetPropertyValue()
            # Bound to min/max.
            lims = setting['values']
            value = sorted(lims + (value,))[1]
        elif setting['type'] in (str(str), 'str'):
            # Limit string length.
            value = value[0, setting['values']]
        elif setting['type'] in (str(bool), 'bool'):
            value = event.GetPropertyValue()
        else:
            raise Exception('Unsupported type.')

        self.current[name] = value
        if value != self.device.settings[name]:
            prop.SetTextColour(wx.Colour(255, 0, 0))
        else:
            prop.SetTextColour(wx.Colour(0, 0, 0))
        self.grid.SelectProperty(prop)


    def onSave(self, event):
        settings = self.grid.GetPropertyValues()
        for name, value in settings.iteritems():
            if self.settings[name]['type'] == 'enum':
                settings[name] = self.settings[name]['values'][value]
        userConfig.setValue(self.handler.getIdentifier() + '_SETTINGS',
                            settings)


    def updateGrid(self):
        if not self.IsShown():
            return
        self.Freeze()
        grid = self.grid
        self.settings = OrderedDict(self.device.describe_settings())
        self.current.update(self.device.settings)
        # Update all values.
        # grid.SetValues(current)
        # Enable/disable
        for prop in grid.Properties:
            prop.SetTextColour(wx.Colour(0, 0, 0))
            name = prop.GetName()
            desc = self.settings[name]
            if desc['type'] in ('enum'):
                prop.SetChoices([str(v) for v in desc['values']],
                                range(len(desc['values'])))
                prop.SetValue(desc['values'].index(self.current[name]))
            else:
                value = self.current[name]
                if type(value) is long:
                    value = int(value)
                prop.SetValue(value)
            try:
                prop.Enable(not self.settings[name]['readonly'])
            except wx._core.PyAssertionError:
                # Bug in wx in stc.EnsureCaretVisible, could not convert to a long.
                pass
        self.Thaw()


    def populateGrid(self):
        grid = self.grid
        self.settings = OrderedDict(self.device.describe_settings())
        self.current = self.device.get_all_settings()
        for key, desc in self.settings.iteritems():
            value = self.current[key]
            # For some reason, a TypeError is thrown on creation of prop if value
            # is a zero-length string.
            if value == '':
                value  = ' '
            propType = SettingsEditor._SETTINGS_TO_PROPTYPES.get(desc['type'])
            if propType is wx.propgrid.EnumProperty:
                prop = wx.propgrid.EnumProperty(label=key, name=key,
                                                labels=[str(v) for v in desc['values']],
                                                values=range(len(desc['values'])),
                                                value=desc['values'].index(value))
            else:
                try:
                    prop = propType(label=key, name=key, value=(value or 0))
                except OverflowError:
                    # Int too large.
                    prop = wx.propgrid.FloatProperty(label=key, name=key, value=str(value or 0))
                except Exception as e:
                    log.window.write(log.window.stdErr,
                                     "populateGrid threw exception for key %s with value %s: %s" %
                                     (key, value, e.message))
                    continue

            if desc['readonly']:
                prop.Enable(False)
            grid.Append(prop)