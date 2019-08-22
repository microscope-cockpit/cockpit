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


"""Microscope devices.

   Supports devices that implement the interface defined in
   microscope.devices
"""
import Pyro4
import wx
from cockpit import events
from . import device
from cockpit import depot
import cockpit.gui.device
import cockpit.handlers.deviceHandler
import cockpit.handlers.filterHandler
import cockpit.handlers.lightPower
import cockpit.handlers.lightSource
import cockpit.util.colors
import cockpit.util.userConfig
import cockpit.util.threads
from cockpit.gui.device import SettingsEditor
import re

# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

class MicroscopeBase(device.Device):
    """A class to communicate with the UniversalDevice interface."""
    def __init__(self, name, config):
        super(MicroscopeBase, self).__init__(name, config)
        self.handlers = []
        self.panel = None
        # Pyro proxy
        self._proxy = Pyro4.Proxy(config.get('uri'))
        self.settings = {}
        self.cached_settings={}
        self.settings_editor = None
        self.defaults = DEFAULTS_NONE
        self.enabled = True
        self.get_all_settings = self._proxy.get_all_settings
        self.get_setting = self._proxy.get_setting
        self.set_setting = self._proxy.set_setting
        self.describe_settings = self._proxy.describe_settings

    def finalizeInitialization(self):
        super(MicroscopeBase, self).finalizeInitialization()
        # Set default settings on remote device. These will be over-
        # ridden by any defaults in userConfig, later.
        # Currently, settings are an 'advanced' feature --- the remote
        # interface relies on us to send it valid data, so we have to
        # convert our strings to the appropriate type here.
        ss = self.config.get('settings')
        if ss:
            settings = dict([m.groups() for kv in ss.split('\n')
                             for m in [re.match(r'(.*)\s*[:=]\s*(.*)', kv)] if m])
        for k,v in settings.items():
            try:
                desc = self.describe_setting(k)
            except:
                print ("%s ingoring unknown setting '%s'." % (self.name, k))
                continue
            if desc['type'] == 'str':
                pass
            elif desc['type'] == 'int':
                v = int(v)
            elif desc['type'] == 'float':
                v = float(v)
            elif desc['type'] == 'bool':
                v = v.lower() in ['1', 'true']
            elif desc['type'] == 'tuple':
                print ("%s ignoring tuple setting '%s' - not yet supported." % (self.name, k))
                continue
            elif desc['type'] == 'enum':
                if v.isdigit():
                    v = int(v)
                else:
                    vmap = dict((k,v) for v,k in desc['values'])
                    v = vmap.get(v, None)
                if v is None:
                    print ("%s ignoring enum setting '%s' with unrecognised value." % (self.name, k))
                    continue
            self.set_setting(k, v)
        self._readUserConfig()


    def getHandlers(self):
        """Return device handlers. Derived classes may override this."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    def showSettings(self, evt):
        if not self.settings_editor:
            # TODO - there's a problem with abstraction here. The settings
            # editor needs the describe/get/set settings functions from the
            # proxy, but it also needs to be able to invalidate the cache
            # on the handler. The handler should probably expose the
            # settings interface.
            self.setAnyDefaults()
            import collections.abc
            if self.handlers and isinstance(self.handlers, collections.abc.Sequence):
                h = self.handlers[0]
            elif self.handlers:
                h = self.handlers
            else:
                h = None
            parent = evt.EventObject.Parent
            self.settings_editor = SettingsEditor(self, parent, handler=h)
            self.settings_editor.Show()
        self.settings_editor.SetPosition(wx.GetMousePosition())
        self.settings_editor.Raise()


    def updateSettings(self, settings=None):
        if settings is not None:
            self._proxy.update_settings(settings)
        self.settings.update(self._proxy.get_all_settings())
        events.publish(events.SETTINGS_CHANGED % str(self))


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        if self.defaults != DEFAULTS_PENDING:
            # nothing to do
            return
        try:
            self._proxy.update_settings(self.settings)
        except Exception as e:
            print (e)
        else:
            self.defaults = DEFAULTS_SENT


    def _readUserConfig(self):
        idstr = self.name + '_SETTINGS'
        defaults = cockpit.util.userConfig.getValue(idstr)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.settings.update(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


    def onPyroError(self, err, *args):
        """Handle exceptions raised by async. proxy."""
        raise err


class MicroscopeGenericDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


class MicroscopeSwitchableDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def finalizeInitialization(self):
        super(MicroscopeSwitchableDevice, self).finalizeInitialization()
        self.enabled = self._proxy.get_is_enabled()


class MicroscopeLaser(MicroscopeBase):
    """A light source with power control.

    Sample config entry:
      [488nm]
      type: MicroscopeLaser
      uri: PYRO:DeepstarLaser@192.168.0.2:7001
      wavelength: 488
      triggerSource: trigsource
      triggerLine: 1

      [trigsource]
      type: ExecutorDevice
      ...
    """
    def _setEnabled(self, on):
        if on:
            self._proxy.enable()
        else:
            self._proxy.disable()

    def getHandlers(self):
        wl = self.config.get('wavelength', None)
        if wl:
            col = cockpit.util.colors.wavelengthToColor(wl, 0.8)
        else:
            col = '0xaaaaaa'
        """Return device handlers. Derived classes may override this."""
        # Querying remote for maxPower can cause delays, so set to None
        # and update later.
        self.handlers.append(cockpit.handlers.lightPower.LightPowerHandler(
            self.name + ' power',  # name
            self.name + ' light source',  # groupName
            {
                'setPower': cockpit.util.threads.callInNewThread(self._proxy.set_power_mw),
                'getPower': self._proxy.get_power_mw, # Synchronous - can hang threads.
            },
            wl,# wavelength,
            0, None, 20, #minPower, maxPower, curPower,
            col, #colour
            isEnabled=True))
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        self.handlers.append(cockpit.handlers.lightSource.LightHandler(
            self.name,
            self.name + ' light source',
            {'setEnabled': lambda name, on: self._setEnabled(on),
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime},
            self.config.get('wavelength', None),
            100,
            trighandler,
            trigline))

        return self.handlers


    def finalizeInitialization(self):
        # This should probably work the other way around:
        # after init, the handlers should query for the current state,
        # rather than the device pushing state info to the handlers as
        # we currently do here.
        #
        # Query the remote to update max power on handler.
        ph = self.handlers[0] # powerhandler
        ph.setMaxPower(self._proxy.get_max_power_mw())
        ph.powerSetPoint = self._proxy.get_set_power_mw()
        # Set lightHandler to enabled if light source is on.
        lh = self.handlers[-1]
        lh.state = int(self._proxy.get_is_on())


class MicroscopeFilter(MicroscopeBase):
    def __init__(self, *args, **kwargs):
        super(MicroscopeFilter, self).__init__(*args, **kwargs)
        # Cameras
        cdefs = self.config.get('cameras', None)
        if cdefs:
            self.cameras = re.split('[,;]\s*', cdefs)
        else:
            self.cameras = None

        # Lights
        ldefs = self.config.get('lights', None)
        if ldefs:
            self.lights = re.split('[,;]\s*', ldefs)
        else:
            self.lights = None

        # Filters
        # Used to do this in finalizeInitialization, but there's
        # no obvious reason to do it there, and it occasionally
        # caused a threadpool deadlock.
        fdefs = self.config.get('filters', None)
        if fdefs:
            fdefs = [re.split(':\s*|,\s*', f) for f in re.split('\n', fdefs) if f]
        else:
            fdefs = self._proxy.get_filters()
        if not fdefs:
            raise Exception ("No local or remote filter definitions for %s." % self.name)
        self.filters = [cockpit.handlers.filterHandler.Filter(*f) for f in fdefs]


    def getHandlers(self):
        """Return device handlers."""
        h = cockpit.handlers.filterHandler.FilterHandler(self.name, 'filters', False,
                                                 {'setPosition': self.setPosition,
                                                  'getPosition': self.getPosition,
                                                  'getFilters': self.getFilters},
                                                 self.cameras,
                                                 self.lights)
        self.handlers = [h]
        return self.handlers


    def setPosition(self, position, callback=None):
        asproxy = Pyro4.Proxy(self._proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.set_setting('position', position).then(callback)


    def getPosition(self):
        return self._proxy.get_setting('position')


    def getFilters(self):
        return self.filters
