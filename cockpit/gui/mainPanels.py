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

import wx
from cockpit import depot
from cockpit.handlers.deviceHandler import STATES
from cockpit.util.colors import wavelengthToColor
from cockpit.gui.device import EnableButton
from cockpit.gui import safeControls


class PanelLabel(wx.StaticText):
    def __init__(self, parent, label=""):
        super().__init__(parent, label=label)
        # Can't seem to modify font in-situ: must modify via local ref then re-set.
        font = self.Font.Bold()
        font.SetSymbolicSize(wx.FONTSIZE_X_LARGE)
        self.SetFont(font)


class LightPanel(wx.Panel):
    def __init__(self, parent, lightToggle, lightPower=None, lightFilters=[]):
        super().__init__(parent, style=wx.BORDER_RAISED)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
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

        self.Sizer.Add(wx.StaticText(self, label='exposure / ms'),
                       flag=wx.ALIGN_CENTER_HORIZONTAL)
        self.Sizer.Add(expCtrl, flag=wx.EXPAND)

        if lightPower is not None:
            self.Sizer.AddSpacer(4)
            self.Sizer.Add(wx.StaticText(self, label="power / mW"),
                           flag=wx.ALIGN_CENTER_HORIZONTAL)
            powCtrl = safeControls.SpinGauge(self,
                                             minValue = lightPower.minPower,
                                             maxValue = lightPower.maxPower,
                                             fetch_current=lightPower.getPower)
            lightPower.addWatch('powerSetPoint', powCtrl.SetValue)
            powCtrl.Bind(safeControls.EVT_SAFE_CONTROL_COMMIT,
                         lambda evt: lightPower.setPower(evt.Value))
            self.Sizer.Add(powCtrl)


    def SetFocus(self):
        # Sets focus to the main button to avoid accidental data entry
        # in power or exposure controls.
        self.button.SetFocus()


    def onStatus(self, evt):
        light, state = evt.EventData
        if light != self.light:
            return
        if state == STATES.enabling:
            self.button.Disable()
            self.button.SetBitmap(BMP_WAIT)
        else:
            self.button.Enable()
        if state == STATES.enabled:
            self.button.SetBitmap(BMP_ON)
        elif state == STATES.disabled:
            self.button.SetBitmap(BMP_OFF)
        elif state == STATES.error:
            self.button.SetBitmap(BMP_ERR)


class LightControlsPanel(wx.Panel):
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
            sz.Add(panel)
            self.panels[light] = panel
            sz.AddSpacer(4)
        self.Fit()



class CameraPanel(wx.Panel):
    def __init__(self, parent, camera):
        super().__init__(parent, style=wx.BORDER_RAISED)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        self.camera = camera
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.button = EnableButton(self, self.camera)
        self.button.setState(self.camera.state)
        self.Sizer.Add(self.button, flag=wx.EXPAND)
        self.Sizer.AddSpacer(2)

        line = wx.StaticBox(self, size=(-1,4), style=wx.LI_HORIZONTAL)
        line.SetBackgroundColour(wavelengthToColor(self.camera.wavelength or 0))
        self.Sizer.Add(line, flag=wx.EXPAND)
        # If there are problems here, it's because the inline function below is
        # being called outside of the main thread and needs taking out and
        # wrapping with wx.CallAfter.
        camera.addWatch('wavelength',
                        lambda wl: line.SetBackgroundColour(wavelengthToColor(wl or 0)))
        self.Sizer.AddSpacer(2)

        if hasattr(camera, 'modes'):
            print("Has modes")
            modebutton = wx.Button(parent, label='Mode')
            self.Sizer.Add(modebutton)

        if camera.callbacks.get('makeUI', None):
            self.Sizer.Add(camera.callbacks['makeUI'](self))
        self.Sizer.AddSpacer(2)


    def SetFocus(self):
        # Sets focus to the main button to avoid accidental data entry
        # in power or exposure controls.
        self.button.SetFocus()

    def onStatus(self, evt):
        camera, state = evt.EventData
        if camera != self.camera:
            return
        if state == STATES.enabling:
            self.button.Disable()
            self.button.SetBitmap(BMP_WAIT)
        else:
            self.button.Enable()
        if state == STATES.enabled:
            self.button.SetBitmap(BMP_ON)
        elif state == STATES.disabled:
            self.button.SetBitmap(BMP_OFF)
        elif state == STATES.error:
            self.button.SetBitmap(BMP_ERR)


class CameraControlsPanel(wx.Panel):
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
            sz.Add(panel)
            self.panels[cam] = panel
            sz.AddSpacer(4)
        self.Fit()