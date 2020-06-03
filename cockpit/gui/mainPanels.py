#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018-19 Mick Phillips <mick.phillips@gmail.com>
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

import typing

import wx

import cockpit.interfaces.channels
from cockpit import depot, events
from cockpit.util.colors import wavelengthToColor
from cockpit.gui.device import EnableButton
from cockpit.gui import safeControls


class PanelLabel(wx.StaticText):
    """A formatted label for panels of controls."""
    def __init__(self, parent, label=""):
        super().__init__(parent, label=label)
        # Can't seem to modify font in-situ: must modify via local ref then re-set.
        font = self.Font.Bold()
        font.SetSymbolicSize(wx.FONTSIZE_X_LARGE)
        self.SetFont(font)


class LightPanel(wx.Panel):
    """A panel of controls for a single light source."""
    def __init__(self, parent, lightToggle, lightPower=None, lightFilters=[]):
        super().__init__(parent, style=wx.BORDER_RAISED)
        self.light = lightToggle
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.button = EnableButton(self, self.light)
        self.button.setState(self.light.state)

        expCtrl = safeControls.SafeSpinCtrlDouble(self, inc=5)
        expCtrl.Bind(safeControls.EVT_SAFE_CONTROL_COMMIT,
                          lambda evt: self.light.setExposureTime(evt.Value))
        lightToggle.addWatch('exposureTime', expCtrl.SetValue)
        expCtrl.SetValue(lightToggle.exposureTime)

        self.Sizer.Add(self.button, flag=wx.EXPAND)
        self.Sizer.AddSpacer(2)
        line = wx.StaticBox(self, size=(-1,4), style=wx.LI_HORIZONTAL)
        line.SetBackgroundColour(wavelengthToColor(self.light.wavelength))
        self.Sizer.Add(line, flag=wx.EXPAND)

        self.Sizer.Add(wx.StaticText(self, label='Exposure / ms'),
                       flag=wx.ALIGN_CENTER_HORIZONTAL)
        self.Sizer.Add(expCtrl, flag=wx.EXPAND)

        if lightPower is not None:
            self.Sizer.AddSpacer(4)
            self.Sizer.Add(wx.StaticText(self, label="Power / mW"),
                           flag=wx.ALIGN_CENTER_HORIZONTAL)
            powCtrl = safeControls.SpinGauge(self,
                                             minValue = lightPower.minPower,
                                             maxValue = lightPower.maxPower,
                                             fetch_current=lightPower.getPower)
            powCtrl.SetValue(lightPower.powerSetPoint)
            lightPower.addWatch('powerSetPoint', powCtrl.SetValue)
            powCtrl.Bind(safeControls.EVT_SAFE_CONTROL_COMMIT,
                         lambda evt: lightPower.setPower(evt.Value))
            self.Sizer.Add(powCtrl)

        if lightFilters:
            self.Sizer.AddSpacer(4)
            self.Sizer.Add(wx.StaticText(self, label="Filters"),
                           flag=wx.ALIGN_CENTER_HORIZONTAL)
            for f in lightFilters:
                self.Sizer.Add(f.makeSelector(self), flag=wx.EXPAND)


    def SetFocus(self):
        # Sets focus to the main button to avoid accidental data entry
        # in power or exposure controls.
        self.button.SetFocus()


    def onStatus(self, evt):
        light, state = evt.EventData
        if light != self.light:
            return
        self.button.setState(state)


class LightControlsPanel(wx.Panel):
    """Creates a LightPanel for each light source."""
    def __init__(self, parent):
        super().__init__(parent)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(PanelLabel(self, label="Lights"))
        sz = wx.BoxSizer(wx.HORIZONTAL)
        self.Sizer.Add(sz)

        lightToggles = sorted(depot.getHandlersOfType(depot.LIGHT_TOGGLE),
                              key=lambda l: l.wavelength)
        lightPowers = depot.getHandlersOfType(depot.LIGHT_POWER)
        lightFilters = list(filter(lambda f: f.lights,
                                   depot.getHandlersOfType(depot.LIGHT_FILTER)))
        self.panels = {}
        for light in lightToggles:
            power = next(filter(lambda p: p.groupName == light.groupName, lightPowers), None)
            filters = list(filter(lambda f: light.name in f.lights, lightFilters) )
            panel = LightPanel (self, light, power, filters)
            sz.Add(panel, flag=wx.EXPAND)
            self.panels[light] = panel
            sz.AddSpacer(4)
        self.Fit()


class CameraPanel(wx.Panel):
    """A panel of controls for a single camera."""
    def __init__(self, parent, camera):
        super().__init__(parent, style=wx.BORDER_RAISED)
        self.camera = camera
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.button = EnableButton(self, self.camera)
        self.button.setState(self.camera.state)
        self.Sizer.Add(self.button, flag=wx.EXPAND)
        self.Sizer.AddSpacer(2)

        self.line = wx.StaticBox(self, size=(-1,4), style=wx.LI_HORIZONTAL)
        self.line.SetBackgroundColour(wavelengthToColor(self.camera.wavelength or 0))
        self.Sizer.Add(self.line, flag=wx.EXPAND)
        # If there are problems here, it's because the inline function below is
        # being called outside of the main thread and needs taking out and
        # wrapping with wx.CallAfter.
        camera.addWatch('wavelength', self.onWavelengthChange)
        self.Sizer.AddSpacer(2)

        if hasattr(camera, 'modes'):
            modebutton = wx.Button(parent, label='Mode')
            self.Sizer.Add(modebutton)

        if camera.callbacks.get('makeUI', None):
            self.Sizer.Add(camera.callbacks['makeUI'](self))
        self.Sizer.AddSpacer(2)


    def onWavelengthChange(self, wl):
        """Change the colour of our wavelength indicator."""
        self.line.SetBackgroundColour(wavelengthToColor(wl or 0))
        # Explicit refresh required under MSW.
        wx.CallAfter(self.line.Refresh)

    def SetFocus(self):
        # Sets focus to the main button to avoid accidental data entry
        # in power or exposure controls.
        self.button.SetFocus()

    def onStatus(self, evt):
        camera, state = evt.EventData
        if camera != self.camera:
            return
        self.button.setState(state)


class CameraControlsPanel(wx.Panel):
    """Creates a CameraPanel for each camera."""
    def __init__(self, parent):
        super().__init__(parent)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        sz = wx.BoxSizer(wx.HORIZONTAL)
        label = PanelLabel(self, label="Cameras")
        self.Sizer.Add(label)
        self.Sizer.Add(sz)

        cameras = sorted(depot.getHandlersOfType(depot.CAMERA),
                              key=lambda c: c.name)

        self.panels = {}

        for cam in cameras:
            panel = CameraPanel (self, cam)
            sz.Add(panel, flag=wx.EXPAND)
            self.panels[cam] = panel
            sz.AddSpacer(4)
        self.Fit()


class ObjectiveControls(wx.Panel):
    """A panel with an objective selector."""
    def __init__(self, parent):
        super().__init__(parent)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        label = PanelLabel(self, label="Objective")
        self.Sizer.Add(label)
        panel = wx.Panel(self, style=wx.RAISED_BORDER)
        self.Sizer.Add(panel, 1, wx.EXPAND)
        panel.Sizer =  wx.BoxSizer(wx.VERTICAL)

        for o in depot.getHandlersOfType(depot.OBJECTIVE):
            ctrl = wx.Choice(panel)
            ctrl.Set(o.sortedObjectives)
            panel.Sizer.Add(ctrl)
            ctrl.Bind(wx.EVT_CHOICE, lambda evt: o.changeObjective(evt.GetString()))
            events.subscribe("objective change",
                             lambda *a, **kw: ctrl.SetSelection(ctrl.FindString(a[0])))


class FilterControls(wx.Panel):
    """A panel with controls for all filter wheels."""
    def __init__(self, parent):
        super().__init__(parent)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(PanelLabel(self, label="Filters"))
        subpanel = wx.Panel(self, style=wx.BORDER_RAISED)
        self.Sizer.Add(subpanel, 1, wx.EXPAND)
        subpanel.Sizer = wx.WrapSizer(orient=wx.VERTICAL)

        filters = depot.getHandlersOfType(depot.LIGHT_FILTER)
        if not filters:
            self.Hide()
            return

        for i, f in enumerate(filters):
            subpanel.Sizer.Add(f.makeUI(subpanel), 0,
                               wx.EXPAND | wx.RIGHT | wx.BOTTOM, 8)


class ChannelsPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        label = PanelLabel(self, label="Channels")
        self._buttons_sizer = wx.WrapSizer(wx.VERTICAL)

        for name in wx.GetApp().Channels.Names:
            self.AddButton(name)

        wx.GetApp().Channels.Bind(cockpit.interfaces.channels.EVT_CHANNEL_ADDED,
                                  self.OnChannelAdded)
        wx.GetApp().Channels.Bind(cockpit.interfaces.channels.EVT_CHANNEL_REMOVED,
                                  self.OnChannelRemoved)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label)
        sizer.Add(self._buttons_sizer, flag=wx.EXPAND)
        self.SetSizer(sizer)


    def Refresh(self, *args, **kwargs) -> None:
        super().Refresh(*args, **kwargs)
        self.Layout()
        self.Fit()

    def AddButton(self, name: str) -> None:
        button = wx.Button(self, label=name)
        button.Bind(wx.EVT_BUTTON, self.OnButton)
        self._buttons_sizer.Add(button, flag=wx.EXPAND)
        self.Refresh()


    def GetButtonByLabel(self, name: str) -> wx.Button:
        for sizer_item in self._buttons_sizer.Children:
            if sizer_item.Window.LabelText == name:
                return sizer_item.Window
        else:
            raise ValueError('There is no button named \'%s\''
                             % channel_name)


    def OnChannelAdded(self, event: wx.CommandEvent) -> None:
        channel_name = event.GetString()
        self.AddButton(channel_name)

    def OnChannelRemoved(self, event: wx.CommandEvent) -> None:
        channel_name = event.GetString()
        button = self.GetButtonByLabel(channel_name)
        self._buttons_sizer.Detach(button)
        self.Refresh()


    def OnButton(self, event: wx.CommandEvent) -> None:
        """Apply channel with same name as the button."""
        name = event.EventObject.Label
        channel = wx.GetApp().Channels.Get(name)
        cockpit.interfaces.channels.ApplyChannel(channel)
