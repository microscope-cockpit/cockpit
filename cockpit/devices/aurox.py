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
from cockpit.handlers.filterHandler import Filter
import wx

class Clarity(microscopeDevice.MicroscopeFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setEnabled(self, state):
        if state:
            self._proxy.enable()
        else:
            self._proxy.disable()

    def getHandlers(self):
        """Return device handlers."""
        h = super().getHandlers()[0]
        h.callbacks['getIsEnabled'] = self._proxy.get_is_enabled
        h.callbacks['setEnabled'] = self.setEnabled
        return self.handlers

    def set_slide(self, arg):
        print(arg)

    def makeUI(self, parent):
        panel = wx.Panel(parent, style=wx.BORDER_RAISED)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        # power button
        panel.Sizer.Add(cockpit.gui.device.EnableButton(panel, self.handlers[0]))
        # filter control
        panel.Sizer.Add(self.handlers[0].makeSelector(panel))
        # sectioning control
        #ctrl = wx.Choice(panel)
        #ctrl.Set(list(map(str, [Filter(pos, s) for (pos, s) in self._proxy.get_slides().items()])))
        #ctrl.Bind(wx.EVT_CHOICE, lambda evt: self._proxy.set_slide_position(self.filters[evt.Selection]))
        #ctrl.Bind(wx.EVT_CHOICE, lambda evt: self.set_slide(evt.String))
        #ctrl.SetSelection(ctrl.FindString(str(self.lastFilter)))
        #panel.Sizer.Add(ctrl)
        panel.Fit()
        return panel
