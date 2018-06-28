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


from . import deviceHandler
from cockpit import depot
from cockpit import events
import cockpit.gui
import wx

class Filter(object):
    """An individual filter."""

    def __init__(self, position, *args):
        self.position = int(position)
        # args describes the filter.
        # The description can be one of
        #   label, value
        #   (label, value)
        #   label
        if isinstance(args[0], tuple):
            self.label = args[0][0]
            if len(args[0]) > 1:
                self.value = args[0][1]
            else:
                self.value = None
        else:
            self.label = args[0]
            self.value = args[1]

    def __repr__(self):
        if self.value:
            return '%d: %s, %s' % (self.position, self.label, self.value)
        else:
            return '%d: %s' % (self.position, self.label)


class FilterHandler(deviceHandler.DeviceHandler):
    """A handler for emission and ND filter wheels."""
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks, cameras, lights):
        deviceHandler.DeviceHandler.__init__(self,
                                             name, groupName,
                                             isEligibleForExperiments,
                                             callbacks,
                                             depot.LIGHT_FILTER)
        self.cameras = cameras or []
        self.lights = lights or []


    ### UI functions ####
    def makeUI(self, parent):
        self.display = cockpit.gui.toggleButton.ToggleButton(
                        parent=parent, label='', isBold=False)
        self.display.Bind(wx.EVT_LEFT_DOWN, self.menuFunc)
        #self.display.Bind(wx.EVT_RIGHT_DOWN, self._device.showSettings)
        self.updateAfterMove()
        return self.display


    def currentFilter(self):
        position = self.callbacks['getPosition']()
        filters = self.callbacks['getFilters']()
        for f in filters:
            if f.position == position:
                return f


    def updateAfterMove(self, *args):
        # Accept *args so that can be called directly as a Pyro callback
        # or an event handler.
        f = self.currentFilter()
        self.display.SetLabel('%s\n%s' % (self.name, f))
        # Emission filters
        for camera in self.cameras:
            h = depot.getHandler(camera, depot.CAMERA)
            if h is not None:
                h.updateFilter(f.label, f.value)
        # Excitation filters
        for h in self.lights:
            pass


    def menuFunc(self, evt=None):
        items = [str(f) for f in self.callbacks['getFilters']()]
        menu = cockpit.gui.device.Menu(items, self.menuCallback)
        menu.show(evt)


    def menuCallback(self, index, item):
        self.callbacks['setPosition'](index, callback=self.updateAfterMove)
