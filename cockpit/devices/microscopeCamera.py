#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
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


"""Cameras from Python Microscope device server."""

import decimal
import logging

import Pyro4
import wx

from cockpit import depot
import numpy as np
from cockpit import events
import cockpit.gui.device
import cockpit.gui.guiUtils
import cockpit.handlers.camera
import cockpit.util.listener
import cockpit.util.threads
import cockpit.util.userConfig
import cockpit.interfaces.stageMover
from cockpit.devices.microscopeDevice import MicroscopeBase
from cockpit.devices.camera import CameraDevice
from cockpit.handlers.objective import ObjectiveHandler
from cockpit.interfaces.imager import pauseVideo
from cockpit.experiment import experiment
from microscope import Binning, ROI, TriggerMode, TriggerType


_logger = logging.getLogger(__name__)


# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)


def _config_to_ROI(roi_str: str):
    return ROI(*[int(t) for t in roi_str.strip('()').split(',')])


class MicroscopeCamera(MicroscopeBase, CameraDevice):
    """Device class for a remote Python-Microscope camera.

    The default transform and ROI can be configured, in the same
    format as the one used in Python-Microscope.  For example::

        [south camera]
        type: cockpit.devices.microscopeCamera.MicroscopeCamera
        uri: PYRO:SomeCamera@192.168.0.2:7003
        # transform: (lr, ud, rot)
        transform: (1, 0, 0)
        # ROI: (left, top, width, height)
        ROI: (512, 512, 128, 128)

    Guessing the correct transform can be tricky and it's often easier
    to do it by trial and error.  Since this is a fairly specific
    thing that is typically only done once, there isn't a UI on
    Cockpit to do it.  To experiment and find the right transform
    value from Cockpit, open a PyShell from Cockpit (``Ctrl``+``P``)
    and change it manually like so::

        from cockpit import depot
        cam = depot.getDeviceWithName("south camera")
        cam._setTransform((True, False, False))
        cam.softTrigger()
        # If the image displayed is not correct, experiment with
        # other transform, e.g.:
        cam._setTransform((True, True, False))

    """
    def __init__(self, name, config):
        # camConfig is a dict with containing configuration parameters.
        super().__init__(name, config)
        self.enabled = False
        self.panel = None

        if 'roi' in config:
            self._base_ROI = _config_to_ROI(config.get('roi'))
        else:
            self._base_ROI = None

    def initialize(self):
        # Parent class will connect to proxy
        super().initialize()
        # Lister to receive data
        self.listener = cockpit.util.listener.Listener(self._proxy,
                                               lambda *args: self.receiveData(*args))
        try:
            self.updateSettings()
        except:
            pass
        if self.baseTransform:
            self._setTransform(self.baseTransform)
        if self._base_ROI is not None:
            roi = self._proxy.set_roi(self._base_ROI)

    def finalizeInitialization(self):
        super().finalizeInitialization()
        self._readUserConfig()
        # Decorate updateSettings. Can't do this from the outset, as camera
        # is initialized before interfaces.imager.
        self.updateSettings = pauseVideo(self.updateSettings)


    def updateSettings(self, settings=None):
        if settings is not None:
            self._proxy.update_settings(settings)
        self.settings.update(self._proxy.get_all_settings())
        events.publish(events.SETTINGS_CHANGED % str(self))


    def _setTransform(self, tr):
        self._proxy.set_transform(tr)
        self.updateSettings()


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.updateSettings(self.cached_settings)
            #self._proxy.update_settings(self.settings)
            self._proxy.enable()
        self.handler.exposureMode = self._getCockpitExposureMode()


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe(events.CLEANUP_AFTER_EXPERIMENT,
                self.cleanupAfterExperiment)
        events.subscribe(events.OBJECTIVE_CHANGE,
                self.onObjectiveChange)


    def onObjectiveChange(self, handler: ObjectiveHandler) -> None:
        # Changing an objective might change the transform since a
        # different objective might actually mean a different light
        # path (see comments on issue #456).
        self.updateTransform(handler.transform)


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        # TODO - migrate defaults to a universalDevice base class.
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
        idstr = self.handler.getIdentifier() + '_SETTINGS'
        defaults = cockpit.util.userConfig.getValue(idstr)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.updateSettings(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()

    def _getCockpitExposureMode(self) -> int:
        # Cockpit does not support all possible combinations of
        # trigger type and mode from Microscope.
        microscope_trigger_to_cockpit_exposure = {
            (
                TriggerType.SOFTWARE,
                TriggerMode.ONCE,
            ): cockpit.handlers.camera.TRIGGER_SOFT,
            (
                TriggerType.HIGH,
                TriggerMode.ONCE,
            ): cockpit.handlers.camera.TRIGGER_BEFORE,
            (
                TriggerType.LOW,
                TriggerMode.ONCE
            ): cockpit.handlers.camera.TRIGGER_AFTER,
            (
                TriggerType.HIGH,
                TriggerMode.BULB,
            ): cockpit.handlers.camera.TRIGGER_DURATION,
        }
        return microscope_trigger_to_cockpit_exposure[
            (self._proxy.trigger_type, self._proxy.trigger_mode)
        ]

    def getHandlers(self):
        """Return camera handlers."""
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None

        self.handler = cockpit.handlers.camera.CameraHandler(
                "%s" % self.name, "universal camera",
                {'setEnabled': self.enableCamera,
                 'getImageSize': self.getImageSize,
                 'getTimeBetweenExposures': self.getTimeBetweenExposures,
                 'prepareForExperiment': self.prepareForExperiment,
                 'getExposureTime': self.getExposureTime,
                 'setExposureTime': self.setExposureTime,
                 'getShutteringMode': self.getShutteringMode,
                 'getSavefileInfo': self.getSavefileInfo,
                 'setROI': self.setROI,
                 'getROI': self.getROI,
                 'getSensorShape': self.getSensorShape,
                 'makeUI': self.makeUI,
                 'softTrigger': self.softTrigger},
            cockpit.handlers.camera.TRIGGER_SOFT,
            trighandler,
            trigline)

        return [self.handler]


    @pauseVideo
    def enableCamera(self, name, shouldEnable):
        """Enable the hardware."""
        if not shouldEnable:
            # Disable the camera, if it is enabled.
            if self.enabled:
                self.enabled = False
                self._proxy.disable()
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
        asproxy = Pyro4.Proxy(self._proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.enable()
        result.wait(timeout=10)
        self.enabled = self._proxy.get_is_enabled()
        if self.enabled:
            self.handler.exposureMode = self._getCockpitExposureMode()
            self.listener.connect()
        self.updateSettings()
        # a hack as the event expects a light handler, but doesnt use it so
        # call with the camera handler. 
        events.publish(events.LIGHT_EXPOSURE_UPDATE,self.handler)
        return self.enabled


    def getExposureTime(self, name=None, isExact=False):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        t = self._proxy.get_exposure_time()
        if isExact:
            return decimal.Decimal(t) * (decimal.Decimal(1000.0))
        else:
            return t * 1000.0


    def getShutteringMode(self, name):
        """Get the electronic shuttering mode of the camera."""
        return self._proxy.shuttering_mode


    def getImageSize(self, name):
        """Read the image size from the camera."""
        roi = self.getROI(name)
        binning = self._proxy.get_binning()
        if not isinstance(binning, Binning):
            _logger.warning("%s returned tuple not Binning()", self.name)
            binning = Binning(*binning)
        return (roi.width//binning.h, roi.height//binning.v)

    def getROI(self, name):
        """Read the ROI from the camera"""
        roi = self._proxy.get_roi()
        if not isinstance(roi, ROI):
            _logger.warning("%s returned tuple not ROI()", self.name)
            roi = ROI(*roi)
        return roi

    def getSensorShape(self, name):
        """Read the sensor shape from the camera"""
        sensor_shape = self._proxy.get_sensor_shape()
        return sensor_shape

    def getSavefileInfo(self, name):
        """Return an info string describing the measurement."""
        #return "%s: %s image" % (name, self.imageSize)
        return ""


    def getTimeBetweenExposures(self, name, isExact=False):
        """Get the amount of time between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started, in milliseconds."""
        # Camera uses time in s; cockpit uses ms.
        #Note cycle time is exposure+Readout!
        t_cyc = self._proxy.get_cycle_time() * 1000.0
        t_exp = self._proxy.get_exposure_time() * 1000.0
        t = t_cyc - t_exp
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
        if not experiment.isRunning():
            wavelength=None
            if self.handler.wavelength is not None:
                wavelength=float(self.handler.wavelength)
            #not running experiment so populate all data
            metadata={'timestamp': timestamp,
                      'wavelength': wavelength,
                  'pixelsize': wx.GetApp().Objectives.GetPixelSize(),
                  'imagePos': cockpit.interfaces.stageMover.getPosition(),
                  'exposure time': self.getExposureTime(),
                  'lensID': wx.GetApp().Objectives.GetCurrent().lens_ID,
                  'ROI': self.getROI(self.name),
                  }
            #basic heuristic to find excitation wavelength.
            #Finds active lights, sorts in reverse order and then finds the
            #first that is lower than the emission wavelength. 
            lights=[]
            for light in depot.getHandlersOfType('light source'):
                if light.getIsEnabled():
                    lights.append(float(light.wavelength))
                    lights.sort()
                    lights.reverse()
            metadata['exwavelength'] = None
            for exwavelength in lights:
                if (wavelength and
                    wavelength > exwavelength):
                    metadata['exwavelength'] = exwavelength
                    break
        else:
            #experiment running so populate minimum of metadata
            #need to add more but this should equate to the behaviour
            #we had before
            metadata={'timestamp': timestamp,}

        if not isinstance(image, Exception):
            events.publish(events.NEW_IMAGE % self.name, image, metadata)
        else:
            # Handle the dropped frame by publishing an empty image of the correct
            # size. Use the handler to fetch the size, as this will use a cached value,
            # if available.
            events.publish(events.NEW_IMAGE % self.name,
                           np.zeros(self.handler.getImageSize(), dtype=np.int16),
                           metadata)
            raise image


    def setExposureTime(self, name, exposureTime):
        """Set the exposure time."""
        # Camera uses times in s; cockpit uses ms.
        self._proxy.set_exposure_time(exposureTime / 1000.0)


    def setROI(self, name, roi):
        result = self._proxy.set_roi(roi)

        if not result:
            _logger.warning("%s could not set ROI", self.name)

    def softTrigger(self, name=None):
        if self.enabled:
            self._proxy.soft_trigger()


    ### UI functions ###
    def makeUI(self, parent):
        # TODO - this only adds a button with the button for settings.
        # Maybe that should all be handled in CameraPanel since the
        # logic to draw the settings ins the microscope.gui package
        # anyway.
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = wx.Button(parent=self.panel, label='Settings')
        adv_button.Bind(wx.EVT_LEFT_UP, self.showSettings)
        sizer.Add(adv_button, flags=wx.SizerFlags().Expand())
        self.panel.SetSizer(sizer)
        return self.panel
