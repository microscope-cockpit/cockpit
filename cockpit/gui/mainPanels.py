#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import wx

import cockpit.interfaces.channels
from cockpit import depot
from cockpit.util.colors import wavelengthToColor
from cockpit.gui.device import EnableButton
from cockpit.gui import safeControls


class PanelLabel(wx.StaticText):
    """A formatted label for panels of controls."""
    def __init__(self, parent, label=""):
        super().__init__(parent, label=label)
        self.SetFont(self.GetFont().Bold().Larger().Larger())


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
        line_height = int(self.GetFont().GetFractionalPointSize() / 2.0)
        line = wx.Control(self, size=(-1, line_height))
        line.SetBackgroundColour(wavelengthToColor(self.light.wavelength))
        self.Sizer.Add(line, flag=wx.EXPAND)

        self.Sizer.Add(wx.StaticText(self, label='Exposure / ms'),
                       flag=wx.ALIGN_CENTER_HORIZONTAL)
        self.Sizer.Add(expCtrl, flag=wx.EXPAND)

        if lightPower is not None:
            self.Sizer.AddSpacer(4)
            self.Sizer.Add(wx.StaticText(self, label='Power (%)'),
                           flag=wx.ALIGN_CENTER_HORIZONTAL)
            powCtrl = safeControls.SpinGauge(self, minValue=0.0, maxValue=100.0,
                                             fetch_current=lambda: lightPower.getPower()*100.0)
            powCtrl.SetValue(lightPower.powerSetPoint *100.0)
            lightPower.addWatch('powerSetPoint',
                                lambda p: powCtrl.SetValue(p *100.0))
            powCtrl.Bind(safeControls.EVT_SAFE_CONTROL_COMMIT,
                         lambda evt: lightPower.setPower(evt.Value /100.0))
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

        line_height = int(self.GetFont().GetFractionalPointSize() / 2.0)
        self.line = wx.Control(self, size=(-1, line_height))
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
    def __init__(
        self,
        parent: wx.Window,
        interface: cockpit.interfaces.Objectives,
    ) -> None:
        super().__init__(parent)
        self._interface = interface
        label = PanelLabel(self, label="Objective")
        self._choice = wx.Choice(self, choices=interface.GetNamesSorted())
        if not self._choice.SetStringSelection(interface.GetName()):
            raise Exception(
                "failed to find objective '%s'" % interface.GetName()
            )

        self._choice.Bind(wx.EVT_CHOICE, self._OnObjectiveChoice)
        self._interface.Bind(
            cockpit.interfaces.EVT_OBJECTIVE_CHANGED,
            self._OnObjectiveChanged,
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label)
        sizer.Add(self._choice)
        self.SetSizer(sizer)

    def _OnObjectiveChoice(self, event: wx.CommandEvent) -> None:
        self._interface.ChangeObjective(event.GetString())

    def _OnObjectiveChanged(self, event: wx.CommandEvent) -> None:
        if not self._choice.SetStringSelection(event.GetString()):
            raise Exception("failed to find objective '%s'" % event.GetString())
        event.Skip()


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
        sizer.Add(self._buttons_sizer, wx.SizerFlags().Expand())
        self.SetSizer(sizer)


    def _LayoutWithFrame(self):
        self.Layout()
        # When we add a new button, we may require a new column.  When
        # that happens, it's not enough to call Layout(), the parent
        # sizer also needs to make space for our new needs, which
        # comes all the way up from the frame sizer itself, which is
        # why also call Layout() on the Frame. See
        # https://stackoverflow.com/questions/62411713
        frame = wx.GetTopLevelParent(self)
        frame.Layout()
        # But even calling Layout() on the frame may not be enough if
        # the frame itself needs to be resized.  But we can't just
        # call Fit() otherwise we may shrink the window.  We only want
        # to make it wider if required.
        if frame.BestSize[0] > frame.Size[0]:
            frame.SetSize(frame.BestSize[0], frame.Size[1])

    def AddButton(self, name: str) -> None:
        button = wx.Button(self, label=name)
        button.Bind(wx.EVT_BUTTON, self.OnButton)
        self._buttons_sizer.Add(button, wx.SizerFlags().Expand())
        self._LayoutWithFrame()

    def RemoveButton(self, name: str) -> None:
        button = self.GetButtonByLabel(name)
        self._buttons_sizer.Detach(button)
        button.Destroy()
        self._LayoutWithFrame()

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
        self.RemoveButton(channel_name)

    def OnButton(self, event: wx.CommandEvent) -> None:
        """Apply channel with same name as the button."""
        name = event.EventObject.Label
        channel = wx.GetApp().Channels.Get(name)
        cockpit.interfaces.channels.ApplyChannel(channel)
