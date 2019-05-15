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

from . import microscopeDevice
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

    def makeUI(self, parent):
        # The Clarity device draws the UI, so return None from this handler.
        return None


class Clarity(microscopeDevice.MicroscopeFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def checkStatus(self, event):
        busy = False
        try:
            status = self._proxy.get_status()
        except:
            state = STATES.error
            status = {}
        else:
            if status.get('on'):
                state = STATES.enabled
                filter = status.get('filter')
                slide = status.get('slide')
                busy = any(t == (None, 'moving') for t in [filter, slide])
            else:
                state = STATES.disabled
        for h in self.handlers:
            if busy:
                events.publish(events.DEVICE_STATUS, h, STATES.busy)
            else:
                events.publish(events.DEVICE_STATUS, h, state)
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
        panel = wx.Panel(parent, style=wx.BORDER_RAISED)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        # power button
        powerhandler = next(h for h in self.handlers if isinstance(h, ClaritySlideHandler))
        ctrl = cockpit.gui.device.EnableButton(panel, powerhandler)
        panel.Sizer.Add(ctrl, flag=wx.EXPAND)
        # selector controls
        for h in self.handlers:
            panel.Sizer.AddSpacer(8)
            panel.Sizer.Add(h.makeSelector(panel), flag=wx.EXPAND)
        # Start a timer to report connection errors.
        self._timer = wx.Timer(panel)
        self._timer.Start(1000)
        panel.Bind(wx.EVT_TIMER, self.checkStatus, self._timer)
        panel.Fit()
        return panel
