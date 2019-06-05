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
            if len(args) > 1:
                self.value = args[1]
            else:
                self.value = None

            
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
        self.lastFilter = None

        #subscribe to save and load setting calls to enabvle saving and
        #loading of configurations.
        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)

    @property
    def filters(self):
        return self.callbacks['getFilters']()

    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.currentFilter()

    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            self.setFilter(settings[self.name])


    ### UI functions ####
    def makeSelector(self, parent):
        ctrl = wx.Choice(parent)
        ctrl.Set(list(map(str, self.filters)))
        ctrl.Bind(wx.EVT_CHOICE, lambda evt: self.setFilter(self.filters[evt.Selection]))
        self.addWatch('lastFilter', lambda f: ctrl.SetSelection(ctrl.FindString(str(f))))
        ctrl.SetSelection(ctrl.FindString(str(self.lastFilter)))
        return ctrl


    def makeUI(self, parent):
        panel = wx.Panel(parent)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel.Sizer.Add(wx.StaticText(panel, label=self.name))
        panel.Sizer.Add(self.makeSelector(panel), flag=wx.EXPAND)
        return panel


    def setFilter(self, filter):
        self.callbacks['setPosition'](filter.position, callback=self.updateAfterMove)


    def currentFilter(self):
        position = self.callbacks['getPosition']()
        filters = self.callbacks['getFilters']()
        for f in filters:
            if f.position == position:
                return f


    def updateAfterMove(self, *args):
        # Accept *args so that can be called directly as a Pyro callback
        # or an event handler.
        self.lastFilter = self.currentFilter()
        # Emission filters
        for camera in self.cameras:
            h = depot.getHandler(camera, depot.CAMERA)
            if h is not None:
                h.updateFilter(self.lastFilter.label, self.lastFilter.value)
        # Excitation filters
        for h in self.lights:
            pass


    def finalizeInitialization(self):
        self.updateAfterMove()
