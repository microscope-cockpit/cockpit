#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 Mick Phillips <mick.phillips@gmail.com>
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

from cockpit.devices import microscopeDevice
import cockpit.gui.device
import cockpit.handlers.filterHandler
from cockpit.handlers.deviceHandler import STATES
from cockpit.handlers.filterHandler import FilterHandler, Filter
from cockpit import depot
from cockpit import events
import wx


class ClaritySlideHandler(FilterHandler):
    def __init__(self, *args, **kwargs):
        """Subclass FilterHandler for Clarity slider position"""
        # This gives us a filter-like UI for the slider.
        super().__init__(*args, **kwargs)
        # Over-ride the deviceType so that this handler is not added
        # to the filters panel.
        self.deviceType = depot.GENERIC_DEVICE

    def makeUI(self, *args):
        # return None to prevent the slide controls being placed in their
        # own panel - the Clarity device draws the UI for this handler.
        return None


class Clarity(microscopeDevice.MicroscopeFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def checkStatus(self, event):
        busy = False
        try:
            status = self._proxy.get_status()
        except:
            status = {}
        connected = status.get('connected', False)
        mode_selector = self.buttons['mode']
        mode_selector.SetSelection(mode_selector.FindString(status.get('mode', '')))
        self.panel.Enable(connected)
        if not connected:
            state = STATES.error
        else:
            if status['on'] and status['busy']:
                state = STATES.busy
            elif status['on']:
                state = STATES.enabled
            else:
                state = STATES.disabled
            self.buttons['door'].SetValue(status['door open'])
        for h in self.handlers:
            events.publish(events.DEVICE_STATUS, h, state)
            if state not in [STATES.error, STATES.busy]:
                h.updateAfterMove()

    def setEnabled(self, state):
        if state:
            self._proxy.enable()
        else:
            self._proxy.disable()

    def getHandlers(self):
        """Return device handlers."""
        super().getHandlers()
        h = ClaritySlideHandler(self.name + "_slide", 'clarity', False,
                                {'setPosition': self.set_slide_position,
                                 'getPosition': self._proxy.get_slide_position,
                                 'getFilters': self.get_slides_as_filters,
                                 'getIsEnabled': self._proxy.get_is_enabled,
                                 'setEnabled': self.setEnabled},
                                 [],
                                 [])
        self.handlers.append(h)
        return self.handlers

    def set_slide_position(self, position, callback=None):
        import Pyro4
        asproxy = Pyro4.Proxy(self._proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.set_slide_position(position).then(callback)

    def get_slides_as_filters(self):
        return [Filter(k, v) for k, v in self._proxy.get_slides().items()]

    def makeUI(self, parent):
        """Draw the Clarity's UI"""
        # Use an outer panel and a subpanel, so that the power button
        # can en/disable all other controls by managing the state of the
        # subpanel.
        # One minor issue is that the power button doesn't en/disable the
        # Clarity's filter control on the Filters panel, but resolving that
        # is not straightforward. If that control is used to select a filter
        # when the Clarity is not enabled, it will not change the filter, and
        # will redisplay its original state within 1 second.
        outer = wx.Panel(parent, style=wx.BORDER_RAISED)
        outer.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(outer)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        # power button
        powerhandler = next(h for h in self.handlers if isinstance(h, ClaritySlideHandler))
        enable = cockpit.gui.device.EnableButton(outer, powerhandler)
        enable.SetLabel("enable")
        outer.Sizer.Add(enable, flag=wx.EXPAND)
        enable.manageStateOf(panel)
        # Subpanel
        outer.Sizer.Add(panel)
        # slide selector
        panel.Sizer.AddSpacer(4)
        panel.Sizer.Add(wx.StaticText(panel, label='sectioning'))
        panel.Sizer.Add(powerhandler.makeSelector(panel), flag=wx.EXPAND)
        # # filter selector -- moved to filters panel
        # panel.Sizer.AddSpacer(4)
        # panel.Sizer.Add(wx.StaticText(panel, label='filter'))
        # filterhandler = next(h for h in self.handlers if h is not powerhandler)
        # panel.Sizer.Add(filterhandler.makeSelector(panel), flag=wx.EXPAND)
        # Additional buttons
        panel.Sizer.AddSpacer(4)
        self.buttons = {}
        # Mode selector
        panel.Sizer.AddSpacer(4)
        panel.Sizer.Add(wx.StaticText(panel, label='Mode'))
        mode_selector = cockpit.gui.device.EnumChoice(panel)
        mode_selector.Set(self.describe_setting('mode')['values'])
        self.buttons['mode'] = mode_selector
        from functools import partial
        mode_selector.setOnChoice(partial(self.set_setting, 'mode'))
        panel.Sizer.Add(mode_selector)
        # door status indicator
        cb = wx.CheckBox(panel, wx.ID_ANY, "door open")
        cb.Disable()
        self.buttons['door'] = cb
        panel.Sizer.Add(cb)
        # Start a timer to report connection errors.
        self._timer = wx.Timer(panel)
        self._timer.Start(1000)
        panel.Bind(wx.EVT_TIMER, self.checkStatus, self._timer)
        panel.Fit()
        self.panel = panel
        return outer
