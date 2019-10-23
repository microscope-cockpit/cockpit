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


"""MicroscopeCamera device.

  Supports cameras which implement the interface defined in
  microscope.camera.Camera ."""

import decimal
import Pyro4
import wx

from cockpit import depot
import numpy as np
from cockpit import events
import cockpit.gui.device
import cockpit.gui.guiUtils
import cockpit.handlers.camera
import cockpit.util.listener
import cockpit.util.logger
import cockpit.util.threads
import cockpit.util.userConfig
from cockpit.devices.microscopeDevice import MicroscopeBase
from cockpit.devices.camera import CameraDevice
from cockpit.interfaces.imager import pauseVideo
from microscope.devices import ROI, Binning

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION, TRIGGER_SOFT) = range(4)
# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)


class MicroscopeCamera(MicroscopeBase, CameraDevice):
    """A class to control remote python microscope cameras."""
    def __init__(self, name, cam_config):
        # camConfig is a dict with containing configuration parameters.
        super().__init__(name, cam_config)
        self.handler = None
        self.enabled = False
        self.panel = None
        self.config = cam_config

        # Pyro proxy
        self.proxy = Pyro4.Proxy(self.uri)
        self.listener = cockpit.util.listener.Listener(self.proxy,
                                               lambda *args: self.receiveData(*args))
        self.cached_settings={}
        self.settings_editor = None
        self.defaults = DEFAULTS_NONE
        self.get_all_settings = self.proxy.get_all_settings
        self.get_setting = self.proxy.get_setting
        self.set_setting = self.proxy.set_setting
        self.describe_setting = self.proxy.describe_setting
        self.describe_settings = self.proxy.describe_settings
        try:
            self.updateSettings()
        except:
            pass
        if 'readout mode' in self.settings:
            self.modes = self.describe_setting('readout mode')['values']
        else:
            self.modes = []


    @property
    def _modenames(self):
        # Modes are a descriptive string of the form
        # [amp-type] [freq] [channel]
        if not self.modes:
            return ['default']
        import re
        channels = set()
        chre = re.compile(r' CH([0-9]+)', re.IGNORECASE)
        ampre = re.compile(r'CONVENTIONAL ', re.IGNORECASE)
        modes = []
        for i, m in self.modes:
            modes.append(ampre.sub('CONV ', m))
            match = chre.search(m)
            if match:
                channels.union(match.groups())

        if len(channels) < 2:
            modes = [chre.sub('', m) for m in modes]
        return modes

    def finalizeInitialization(self):
        super(MicroscopeCamera, self).finalizeInitialization()
        self._readUserConfig()
        # Decorate updateSettings. Can't do this from the outset, as camera
        # is initialized before interfaces.imager.
        self.updateSettings = pauseVideo(self.updateSettings)


    def updateSettings(self, settings=None):
        if settings is not None:
            self.proxy.update_settings(settings)
        self.settings.update(self.proxy.get_all_settings())
        events.publish(events.SETTINGS_CHANGED % str(self))


    def _setTransform(self, tr):
        self.proxy.set_transform(tr)
        self.updateSettings()


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.updateSettings(self.cached_settings)
            #self.proxy.update_settings(self.settings)
            self.proxy.enable()
        self.handler.exposureMode = self.proxy.get_trigger_type()


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)
        events.subscribe('objective change',
                self.onObjectiveChange)


    def onObjectiveChange(self, name, pixelSize, transform, offset):
        self.updateTransform(transform)


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        # TODO - migrate defaults to a universalDevice base class.
        if self.defaults != DEFAULTS_PENDING:
            # notrhing to do
            return
        try:
            self.proxy.update_settings(self.settings)
        except Exception as e:
            print (e)
        else:
            self.defaults = DEFAULTS_SENT


    def _readUserConfig(self):
        idstr = self.handler.getIdentifier() + '_SETTINGS'
        defaults = cockpit.util.userConfig.getValue(idstr)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.updateSettings(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def getHandlers(self):
        """Return camera handlers."""
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None

        result = cockpit.handlers.camera.CameraHandler(
                "%s" % self.name, "universal camera",
                {'setEnabled': self.enableCamera,
                 'getImageSize': self.getImageSize,
                 'getTimeBetweenExposures': self.getTimeBetweenExposures,
                 'prepareForExperiment': self.prepareForExperiment,
                 'getExposureTime': self.getExposureTime,
                 'setExposureTime': self.setExposureTime,
                 'getImageSizes': self.getImageSizes,
                 'setImageSize': self.setImageSize,
                 'getSavefileInfo': self.getSavefileInfo,
                 'makeUI': self.makeUI,
                 'softTrigger': self.softTrigger},
            TRIGGER_SOFT,
            trighandler,
            trigline)
        # will be set with value from hardware later
        self.handler = result
        return [result]


    @pauseVideo
    def enableCamera(self, name, shouldEnable):
        """Enable the hardware."""
        if not shouldEnable:
            # Disable the camera, if it is enabled.
            if self.enabled:
                self.enabled = False
                self.proxy.disable()
                self.proxy.make_safe()
                self.listener.disconnect()
                return self.enabled

        # Enable the camera
        if self.enabled:
            # Nothing to do.
            return
        self.setAnyDefaults()
        # Use async call to allow hardware time to respond.
        # Pyro4.async API changed - now modifies original rather than returning
        # a copy. This workaround from Pyro4 maintainer.
        asproxy = Pyro4.Proxy(self.proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.enable()
        result.wait(timeout=10)
        #raise Exception("Problem enabling %s." % self.name)
        self.enabled = True
        self.handler.exposureMode = self.proxy.get_trigger_type()
        self.listener.connect()
        self.updateSettings()
        return self.enabled


    def onPyroError(self, err, *args):
        """Handle exceptions raised by aync. proxy."""
        raise err


    def getExposureTime(self, name=None, isExact=False):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        t = self.proxy.get_exposure_time()
        if isExact:
            return decimal.Decimal(t) * (decimal.Decimal(1000.0))
        else:
            return t * 1000.0


    def getImageSize(self, name):
        """Read the image size from the camera."""
        roi = self.proxy.get_roi()  # left, bottom, right, top
        if not isinstance(roi, ROI):
            cockpit.util.logger.log.warning("%s returned tuple not ROI()" % self.name)
            roi = ROI(*roi)
        binning = self.proxy.get_binning()
        if not isinstance(binning, Binning):
            cockpit.util.logger.log.warning("%s returned tuple not Binning()" % self.name)
            binning = Binning(*binning)
        return (roi.width//binning.h, roi.height//binning.v)


    def getImageSizes(self, name):
        """Return a list of available image sizes."""
        return []


    def getSavefileInfo(self, name):
        """Return an info string describing the measurement."""
        #return "%s: %s image" % (name, self.imageSize)
        return ""


    def getTimeBetweenExposures(self, name, isExact=False):
        """Get the amount of time between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started, in milliseconds."""
        # Camera uses time in s; cockpit uses ms.
        t = self.proxy.get_cycle_time() * 1000.0
        if isExact:
            result = decimal.Decimal(t)
        else:
            result = t
        return result


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


    def receiveData(self, *args):
        """This function is called when data is received from the hardware."""
        (image, timestamp) = args
        if not isinstance(image, Exception):
            events.publish('new image %s' % self.name, image, timestamp)
        else:
            # Handle the dropped frame by publishing an empty image of the correct
            # size. Use the handler to fetch the size, as this will use a cached value,
            # if available.
            events.publish('new image %s' % self.name,
                           np.zeros(self.handler.getImageSize(), dtype=np.int16),
                           timestamp)
            raise image


    def setExposureTime(self, name, exposureTime):
        """Set the exposure time."""
        # Camera uses times in s; cockpit uses ms.
        self.proxy.set_exposure_time(exposureTime / 1000.0)


    def setImageSize(self, name, imageSize):
        pass



    def softTrigger(self, name=None):
        if self.enabled:
            self.proxy.soft_trigger()


    ### UI functions ###
    def makeUI(self, parent):
        # TODO - this should probably live in a base deviceHandler.
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Readout mode control
        sizer.Add(wx.StaticText(self.panel, label="Readout mode"))
        modeButton = wx.Choice(self.panel, choices=self._modenames)
        sizer.Add(modeButton, flag=wx.EXPAND)
        events.subscribe(events.SETTINGS_CHANGED % self,
                         lambda: self.updateModeButton(modeButton))
        modeButton.Bind(wx.EVT_CHOICE, lambda evt: self.setReadoutMode(evt.GetSelection()))
        sizer.AddSpacer(4)
        # Gain control
        sizer.Add(wx.StaticText(self.panel, label="Gain"))
        gainButton = wx.Button(self.panel)
        gainButton.Bind(wx.EVT_LEFT_UP, self.onGainButton)
        sizer.Add(gainButton, flag=wx.EXPAND)
        events.subscribe(events.SETTINGS_CHANGED % self,
                         lambda: gainButton.SetLabel("%s" % self.settings.get('gain', None)))
        sizer.AddSpacer(4)
        # Settings button
        adv_button = wx.Button(parent=self.panel, label='settings')
        adv_button.Bind(wx.EVT_LEFT_UP, self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def updateModeButton(self, button):
        button.Set(self._modenames)
        button.SetSelection(self.settings.get('readout mode', 0))


    def onGainButton(self, evt):
        if 'gain' not in self.settings:
            return
        desc = self.describe_setting('gain')
        mingain, maxgain = desc['values']
        gain = wx.GetNumberFromUser('Gain', '', 'Set gain', value=self.settings.get('gain', 0),
                                    min=mingain, max=maxgain)
        if gain == -1:
            return
        self.updateSettings({'gain': gain})


    def onModeButton(self, evt):
        menu = wx.Menu()
        if not self.modes:
            # Camera not enabled yet.
            menu.Append(0, str('No modes known - camera never enabled.'))
            self.panel.Bind(wx.EVT_MENU,  None, id= 0)
        else:
            menuID = 0
            for index, mode in enumerate(self.modes):
                menu.Append(menuID, mode)
                self.panel.Bind(wx.EVT_MENU,
                                lambda event, m=index: self.setReadoutMode(m),
                                id=menuID)
                menuID += 1
        cockpit.gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    @pauseVideo
    def setReadoutMode(self, index):
        if len(self.modes) <= 1:
            # Only one mode - nothing to do.
            return
        self.set_setting('readout mode', self.modes[index][0])
        self.updateSettings()

