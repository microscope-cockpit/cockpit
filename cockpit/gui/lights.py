#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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
from cockpit.events import DEVICE_STATUS
from cockpit.gui import CockpitEvent, EvtEmitter, EVT_COCKPIT, safeControls
from cockpit.handlers.deviceHandler import STATES
from cockpit.util.colors import wavelengthToColor

BMP_SIZE=(16,16)

BMP_OFF = wx.Bitmap.FromRGBA(*BMP_SIZE, red=0, green=32, blue=0,
                             alpha=wx.ALPHA_OPAQUE)
BMP_ON = wx.Bitmap.FromRGBA(*BMP_SIZE, red=0, green=255, blue=0,
                             alpha=wx.ALPHA_OPAQUE)
BMP_WAIT = wx.Bitmap.FromRGBA(*BMP_SIZE, red=255, green=165, blue=0,
                              alpha=wx.ALPHA_OPAQUE)
BMP_ERR = wx.Bitmap.FromRGBA(*BMP_SIZE, red=255, green=0, blue=0,
                             alpha=wx.ALPHA_OPAQUE)

class EnableButton(wx.ToggleButton):
    def __init__(self, parent, deviceHandler):
        super().__init__(parent, -1, deviceHandler.name)
        self.device = deviceHandler
        listener = EvtEmitter(self, DEVICE_STATUS)
        listener.Bind(EVT_COCKPIT, self.onStatusEvent)
        self.SetBitmap(BMP_OFF, wx.RIGHT)
        self.Bind(wx.EVT_TOGGLEBUTTON, deviceHandler.toggleState)

    def onStatusEvent(self, evt):
        device, state = evt.EventData
        if device != self.device:
            return
        if state == STATES.enabling:
            self.Disable()
            self.SetBitmap(BMP_WAIT, wx.RIGHT)
        else:
            self.Enable()
        if state == STATES.enabled:
            self.SetBitmap(BMP_ON, wx.RIGHT)
        elif state == STATES.disabled:
            self.SetBitmap(BMP_OFF, wx.RIGHT)
        elif state == STATES.error:
            self.SetBitmap(BMP_ERR, wx.RIGHT)


class LightPanel(wx.Panel):
    def __init__(self, parent, lightToggle, lightPower=None, lightFilters=[]):
        super().__init__(parent, style=wx.BORDER_RAISED)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        self.light = lightToggle
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.button = EnableButton(self, self.light)

        expCtrl = safeControls.SafeSpinCtrlDouble(self, inc=5)
        expCtrl.Bind(safeControls.EVT_SAFE_CONTROL_COMMIT,
                          lambda evt: self.light.setExposureTime(evt.Value))
        lightToggle.addWatch('exposureTime', expCtrl.SetValue)
        expCtrl.SetValue(lightToggle.exposureTime)

        self.Sizer.Add(self.button, flag=wx.EXPAND)
        self.Sizer.AddSpacer(2)
        line = wx.StaticLine(self, size=(4,4), style=wx.LI_HORIZONTAL)
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
        self.Sizer = wx.BoxSizer(wx.HORIZONTAL)

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
            self.Sizer.Add(panel)
            self.panels[light] = panel
            self.Sizer.AddSpacer(4)
        self.Fit()


