#!/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2016 Mick Phillips (mick.phillips@gmail.com)
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
"""UniversalCamera device.

Supports cameras which implement the interface defined in
  microscope.camera.Camera ."""
import Pyro4
import wx
from config import config
import events
import device
import depot
import gui.device
import gui.guiUtils
import gui.toggleButton
import handlers.deviceHandler
import handlers.filterHandler
import util.listener
import util.userConfig
from gui.device import SettingsEditor
from future.utils import iteritems

CLASS_NAME = 'UniversalDeviceManager'
CONFIG_NAME = 'universal'

# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

# Device types.
(UGENERIC, USWITCHABLE, UDATA, UCAMERA, ULASER, UFILTER) = range(6)

class UniversalBase(device.Device):
    """A class to communicate with the UniversalDevice interface."""
    def __init__(self, name, uri_or_proxy):
        super(UniversalBase, self).__init__()
        self.name = name
        self.handler = None
        self.panel = None
        # Pyro proxy
        # Retain URI support for device creation at command line.
        if isinstance(uri_or_proxy, Pyro4.Proxy):
            self._proxy = uri_or_proxy
        else:
            self._proxy = Pyro4.Proxy(uri_or_proxy)
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
        self.handler = result
        return result


    def showSettings(self, evt):
        if not self.settings_editor:
            # TODO - there's a problem with abstraction here. The settings
            # editor needs the describe/get/set settings functions from the
            # proxy, but it also needs to be able to invalidate the cache
            # on the handler. The handler should probably expose the
            # settings interface. UniversalCamera is starting to look
            # more and more like an interface translation.
            self.setAnyDefaults()
            self.settings_editor = SettingsEditor(self, handler=self.handler)
            self.settings_editor.Show()
        self.settings_editor.SetPosition(wx.GetMousePosition())
        self.settings_editor.Raise()


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        if self.defaults != DEFAULTS_PENDING:
            # nothing to do
            return
        try:
            self._proxy.update_settings(self.settings)
        except Exception as e:
            print e
        else:
            self.defaults = DEFAULTS_SENT


    def onUserLogin(self, username):
        # Apply user defaults on login.
        idstr = self.handler.getIdentifier() + '_SETTINGS'
        defaults = util.userConfig.getValue(idstr, isGlobal=False)
        if defaults is None:
            defaults = util.userConfig.getValue(idstr, isGlobal=True)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.settings.update(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.settings.update(self.cached_settings)
            self._proxy.update_settings(self.settings)
            self._proxy.enable()


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)
        events.subscribe('user login',
                self.onUserLogin)


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


    def onPyroError(self, err, *args):
        """Handle exceptions raised by async. proxy."""
        raise err


class UniversalGenericDevice(UniversalBase):
    def getHandlers(self):
        """Return device handlers."""
        result = handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handler = result
        return result


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



class UniversalSwitchableDevice(UniversalBase):
    def getHandlers(self):
        """Return device handlers."""
        result = handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handler = result
        return result


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
        super(UniversalSwitchableDevice, self).finalizeInitialization()
        self.enabled = self._proxy.get_is_enabled()


class UniversalFilterDevice(UniversalBase):
    def __init__(self, *args, **kwargs):
        super(UniversalFilterDevice, self).__init__(*args, **kwargs)
        # Must be initialized after any drawer.
        self.name = args[0]
        self.priority = 500
        self.cameras = None
        self.lights = None


    def getHandlers(self):
        """Return device handlers."""
        result = handlers.filterHandler.FilterHandler(self, "universal devices")
        self.handler = result
        return result


    def setFilterByIndex(self, index, callback=None):
        # position refers to wheel position.
        # index refers to an element in the list of filters.
        #self._proxy.set_setting('position', self.filters[index].position)
        async = Pyro4.async(self._proxy)
        result = async.set_setting('position',
                                   self.filters[index].position).then(callback)


    def getPosition(self):
        return self._proxy.get_setting('position')


    def getFilter(self):
        position = self.getPosition()
        for f in self.filters:
            if f.position == position:
                return f


    def finalizeInitialization(self):
        self.filters = [handlers.filterHandler.Filter(*f)
                        for f in self._proxy.get_filters()]
        # Read configuration file.
        if config.has_option(self.name, 'camera'):
            cameras = [config.get(self.name, 'camera')]
        elif config.has_option(self.name, 'cameras'):
            cameras = re.split(CONFIG_DELIMETERS, config.get(self.name, 'cameras'))
        else:
            pass
        self.cameras = [c.name for c in depot.getHandlersOfType(depot.CAMERA)]

        if config.has_option(self.name, 'light'):
            lights = [config.get(self.name, 'light')]
        elif config.has_option(self.name, 'lights'):
            lights = re.split(CONFIG_DELIMETERS, config.get(self.name, 'lights'))
        else:
            pass
        self.lights = [c.name for c in depot.getHandlersOfType(depot.CAMERA)]


# Type maps.
ENUM_TO_CLASS = {
    UGENERIC: UniversalGenericDevice,
    USWITCHABLE: UniversalSwitchableDevice,
    UDATA: None,
    UCAMERA: None,
    ULASER: None,
    UFILTER: UniversalFilterDevice,}


class UniversalDeviceManager(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 100
        if not self.isActive:
            return
        self.uris = dict(config.items(CONFIG_NAME))
        self.devices = {}
        for name, uri in iteritems(self.uris):
            proxy = Pyro4.Proxy(uri)
            device_class = ENUM_TO_CLASS[proxy.get_device_type()]
            self.devices[name] = device_class(name, proxy)


    def getHandlers(self):
        """Aggregate and return handlers from managed cameras."""
        result = []
        for name, device in iteritems(self.devices):
            result.append(device.getHandlers())
        return result


    def finalizeInitialization(self):
        for name, device in iteritems(self.devices):
            device.finalizeInitialization()


    def performSubscriptions(self):
        for name, device in iteritems(self.devices):
            device.performSubscriptions()
