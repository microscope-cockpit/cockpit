#!/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2016-2018 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Microscope devices.

   Supports devices that implement the interface defined in
   microscope.devices
"""
import Pyro4
import wx
import events
from . import device
import depot
import gui.device
import gui.guiUtils
import gui.toggleButton
import handlers.deviceHandler
import handlers.filterHandler
import handlers.lightPower
import handlers.lightSource
import util.colors
import util.listener
import util.userConfig
import util.threads
from gui.device import SettingsEditor
import re

# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

# Device types.
(UGENERIC, USWITCHABLE, UDATA, UCAMERA, ULASER, UFILTER) = range(6)

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


    def getHandlers(self):
        """Return device handlers. Derived classes may override this."""
        result = handlers.deviceHandler.DeviceHandler(
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
            # settings interface. UniversalCamera is starting to look
            # more and more like an interface translation.
            self.setAnyDefaults()
            self.settings_editor = SettingsEditor(self, handler=self.handlers[0])
            self.settings_editor.Show()
        self.settings_editor.SetPosition(wx.GetMousePosition())
        self.settings_editor.Raise()


    def updateSettings(self, settings=None):
        if settings is not None:
            self._proxy.update_settings(settings)
        self.settings.update(self._proxy.get_all_settings())
        events.publish("%s settings changed" % str(self))


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


    def onUserLogin(self, username):
        # Apply user defaults on login.
        idstr = self.name + '_SETTINGS'
        defaults = util.userConfig.getValue(idstr, isGlobal=False)
        if defaults is None:
            defaults = util.userConfig.getValue(idstr, isGlobal=True)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.settings.update(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('user login',
                self.onUserLogin)


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


    def onPyroError(self, err, *args):
        """Handle exceptions raised by async. proxy."""
        raise err


class MicroscopeGenericDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = handlers.deviceHandler.DeviceHandler(
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
        adv_button = gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


class MicroscopeSwitchableDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = handlers.deviceHandler.DeviceHandler(
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
        adv_button = gui.device.Button(parent=self.panel,
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
            col = util.colors.wavelengthToColor(wl, 0.8)
        else:
            col = '0xaaaaaa'
        """Return device handlers. Derived classes may override this."""
        self.handlers.append(handlers.lightPower.LightPowerHandler(
            self.name + ' power',  # name
            self.name + ' light source',  # groupName
            {
                'setPower': util.threads.callInNewThread(self._proxy.set_power_mw),
                'getPower': self._proxy.get_power_mw, # Synchronous - can hang threads.
            },
            wl,# wavelength,
            0, 100, 20,#minPower, maxPower, curPower,
            col, #colour
            isEnabled=True))
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        self.handlers.append(handlers.lightSource.LightHandler(
            self.name + ' toggle',
            self.name + ' light source',
            {'setEnabled': lambda name, on: self._setEnabled(on),
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime},
            self.config.get('wavelength', None),
            100,
            trighandler,
            trigline))

        return self.handlers


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

        # Filters - will populate later.
        self.filters = []


    def getHandlers(self):
        """Return device handlers."""
        h = handlers.filterHandler.FilterHandler(self.name, 'filters', False,
                                                 {'setPosition': self.setPosition,
                                                  'getPosition': self.getPosition,
                                                  'getFilters': self.getFilters},
                                                 self.cameras,
                                                 self.lights)
        self.handlers = [h]
        return self.handlers


    def setPosition(self, index, callback=None):
        # position refers to wheel position.
        # index refers to an element in the list of filters.
        #self._proxy.set_setting('position', self.filters[index].position)
        async = Pyro4.Proxy(self._proxy._pyroUri)
        async._pyroAsync()
        result = async.set_setting('position',
                                   self.filters[index].position).then(callback)


    def getPosition(self):
        return self._proxy.get_setting('position')


    def getFilters(self):
        return self.filters


    def finalizeInitialization(self):
        # Filters
        fdefs = self.config.get('filters', None)
        if fdefs:
            fdefs = [re.split(':\s*|,\s*', f) for f in re.split('\n', fdefs) if f]
        else:
            fdefs = self._proxy.get_filters()
        if not fdefs:
            raise Exception ("No local or remote filter definitions for %s." % self.name)
        self.filters = [handlers.filterHandler.Filter(*f) for f in fdefs]


# Type maps.
ENUM_TO_CLASS = {
    UGENERIC: MicroscopeGenericDevice,
    USWITCHABLE: MicroscopeSwitchableDevice,
    UDATA: None,
    UCAMERA: None,
    ULASER: None,
    UFILTER: MicroscopeFilter,}
