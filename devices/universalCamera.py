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


import collections
import decimal
import numpy
import threading
import time
import wx

import camera
import events
import handlers.camera
import gui.device
import gui.guiUtils
import gui.toggleButton
import Pyro4
import util.listener
import util.threads

from config import CAMERAS

CLASS_NAME = 'UniversalCameraManager'

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION, TRIGGER_SOFT) = range(4)


class UniversalCameraDevice(camera.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, cam_config):
        # camConfig is a dict with containing configuration parameters.
        super(UniversalCameraDevice, self).__init__(cam_config)
        self.handler = None        
        self.enabled = False
        self.config = cam_config
        # Pyro proxy
        self.proxy = Pyro4.Proxy('PYRO:%s@%s:%d' % 
                                  ('Device',
                                   cam_config.get('ipAddress') or cam_config.get('host'),
                                   cam_config.get('port')))
        self.listener = util.listener.Listener(self.object, 
                                               lambda *args: self.receiveData(*args))
        self.base_transform = cam_config.get('baseTransform') or (0, 0, 0)
        self.path_transform = (0, 0, 0)
        self.settings = {}
        self.cached_settings={}
        self.settings['transform'] = tuple(
                         path_transform[i] ^ baseTransform[i] for in range(3))
        self.settings['exposure_time'] = 0.001


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.settings.update(self.cached_settings)
            self.proxy.update_settings(self.settings)
            self.object.enable()
        self.handler.exposureMode = self.interactiveTrigger


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)
        events.subscribe('objective change',
                self.onObjectiveChange)


    def onObjectiveChange(self, name, pixelSize, transform, offset):
        self.settings.update({'pathTransform': transform})
        # Apply the change now if the camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)
    

    def getHandlers(self):
        """Return camera handlers."""
        result = handlers.camera.CameraHandler(
                "%s" % self.config.get('label'), "iXon camera",
                {'setEnabled': self.enableCamera,
                    'getImageSize': self.getImageSize,
                    'getTimeBetweenExposures': self.getTimeBetweenExposures,
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize,
                    'getSavefileInfo': self.getSavefileInfo,
                    'makeUI': self.makeUI},
                self.interactiveTrigger)
        self.handler = result
        return result


    def enableCamera(self, name, shouldEnable):
        """Enable the hardware."""
        if not shouldEnable:
            # Disable the camera, if it is enabled.
            if self.enabled:
                self.enabled = False
                self.object.disable()
                self.object.make_safe()
                self.listener.disconnect()
                self.updateUI()
                return

        # Enable the camera
        if self.enabled:
            # Nothing to do.
            return


        originalTimeout = self.object._pyroTimeout
        try:
            self.object._pyroTimeout = 60
            self.object.enable(self.settings)
            self.object._pyroTimeout = originalTimeout
        except Exception as e:
            print e
        else:
            # Wait for camera to show it is enabled.
            while not self.object.is_enabled():
                time.sleep(1)
            self.enabled = True
            # Connect the listener to receive data.
            self.listener.connect()
            # Update our settings with the real settings.
            self.settings.update(self.object.get_settings())
        # Update the UI.
        self.updateUI()


    def getExposureTime(self, name, isExact):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        t = self.object.get_exposure_time()
        if isExact:
            return decimal.Decimal(t) * (decimal.Decimal(1000.0))
        else:
            return t * 1000.0


    def getImageSize(self, name):
        """Read the image size from the camera."""
        return self.object.get_image_size()


    def getImageSizes(self, name):
        """Return a list of available image sizes."""
        return self.imageSizes


    def getSavefileInfo(self, name):
        """Return an info string describing the measurement."""
        if self.settings.get('amplifierMode').get('amplifier') == 0:
            gain = 'EM %d' % self.settings.get('EMGain')
        else:
            gain = 'Conv'
        return "%s: %s gain, %s image" % (name, gain, '512x512')


    def getTimeBetweenExposures(self, name, isExact=False):
        """Get the amount of time between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started, in milliseconds."""
        # Camera uses time in s; cockpit uses ms.
        t = self.object.get_min_time_between_exposures() * 1000.0
        if isExact:
            result = decimal.Decimal(t)
        else:
            result = t
        return result


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)
        self.object.abort()
        self.settings['frameTransfer'] = self.experimentTriggerMode.frameTransfer
        self.settings['fastTrigger'] = self.experimentTriggerMode.fastTrigger
        self.settings['triggerMode'] = self.experimentTriggerMode.cameraTrigger
        try:
            self.object.enable(self.settings)
        except:
            raise
        else:
            self.handler.exposureMode = self.experimentTriggerMode.cockpitTrigger


    def receiveData(self, action, *args):
        """This function is called when data is received from the hardware."""
        # print 'receiveData received %s' % action
        if action == 'new image':
            (image, timestamp) = args
            events.publish('new image %s' % self.name, image, timestamp)


    def setExposureTime(self, name, exposureTime):
        """Set the exposure time."""
        # Camera uses times in s; cockpit uses ms.
        self.settings.update({'exposureTime': exposureTime / 1000.0})
        # Apply the change right now if the camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)


    def setImageSize(self, name, imageSize):
        pass


    ### UI stuff ###
    def onGainButton(self, event=None):
        menu = wx.Menu()
        menuID = 1
        for value in range (0, 255, 10):
            menu.Append(menuID, str(value))
            wx.EVT_MENU(self.panel, menuID, lambda event, value=value: self.setGain(value))
            menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def setGain(self, value):
        self.settings.update({'EMGain': value})
        # Apply the change now if the camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)
        self.updateUI()


    def onModeButton(self, event=None):
        menu = wx.Menu()
        if not self.amplifierModes:
            # Camera not enabled yet.
            menu.Append(0, str('No modes known - camera never enabled.'))
            wx.EVT_MENU(self.panel, 0, None)
        else:
            menuID = 0
            for mode in self.amplifierModes:
                menu.Append(menuID, mode['label'])
                #wx.EVT_MENU(self.panel, menuID, lambda event, n=menuID:
                #            self.setAmplifierMode(n))
                wx.EVT_MENU(self.panel, menuID, lambda event, m=mode:
                            self.setAmplifierMode(m))
                menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def onRightMouse(self, event=None):
        """Present a thermal management menu on right click."""
        menu = wx.Menu()
        menu.SetTitle('Thermal management')

        # Check control to indicate/set water cooling availability.
        menu.AppendCheckItem(0, 'water cooling')
        menu.Check(0, self.settings.get('isWaterCooled', False))
        wx.EVT_MENU(self.panel, 0, lambda event: self.toggleWaterCooling())

        # Submenu of temperature set points.
        tMenu = wx.Menu()
        temperatures = [-40, -50, -60, -70, -80, -90, -100]
        airCooledLimit = -50
        for itemID, t in enumerate(temperatures, 100):
            tMenu.AppendRadioItem(itemID, u'%d°C' % t)
            if t == self.settings['targetTemperature']:
                tMenu.Check(itemID, True)
            if t < airCooledLimit and not self.settings.get('isWaterCooled'):
                tMenu.Enable(itemID, False)
            wx.EVT_MENU(self.panel, itemID, lambda event, target=t: self.setTargetTemperature(target))
            itemID += 1

        menu.AppendSubMenu(tMenu, 'sensor set point')

        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def onTrigButton(self, event=None):
        menu = wx.Menu()
        menuID = 0
        for mode in TRIGGER_MODES:
            menu.Append(menuID, mode.label)
            wx.EVT_MENU(self.panel, menuID, lambda event, m=mode:
                        self.setExperimentTriggerMode(m))
            menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def setExperimentTriggerMode(self, mode):
        self.experimentTriggerMode = mode
        self.trigButton.SetLabel('exp. trigger:\n%s' % mode.label)


    def setAmplifierMode(self, mode):
        self.settings.update({'amplifierMode': mode})
        # Apply the change right now if camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)
        self.updateUI()


    def setTargetTemperature(self, temperature):
        self.settings.update({'targetTemperature': temperature})
        self.object.update_settings({'targetTemperature': temperature})


    def toggleWaterCooling(self):
        newSetting = not self.settings.get('isWaterCooled')
        self.settings.update({'isWaterCooled': newSetting})
        self.object.update_settings({'isWaterCooled': newSetting})


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(
                parent=self.panel, label=self.config['label'])
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.VERTICAL)

        self.modeButton = gui.toggleButton.ToggleButton(
                label="Mode:\n%s" % 'not set',
                parent=self.panel)
        self.modeButton.Bind(wx.EVT_LEFT_DOWN, self.onModeButton)
        self.modeButton.Unbind(wx.EVT_RIGHT_DOWN)
        rowSizer.Add(self.modeButton)

        self.gainButton = gui.toggleButton.ToggleButton(
                label="EM Gain\n%d" % self.settings['EMGain'],
                parent=self.panel)
        self.gainButton.Bind(wx.EVT_LEFT_DOWN, self.onGainButton)
        self.gainButton.Unbind(wx.EVT_RIGHT_DOWN)
        rowSizer.Add(self.gainButton)

        self.trigButton = gui.toggleButton.ToggleButton(
                label='exp. trigger:\n%s' % self.experimentTriggerMode.label,
                parent=self.panel)
        self.trigButton.Bind(wx.EVT_LEFT_DOWN, self.onTrigButton)
        self.trigButton.Unbind(wx.EVT_RIGHT_DOWN)
        rowSizer.Add(self.trigButton)

        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        for child in self.panel.Children:
            child.Bind(wx.EVT_RIGHT_DOWN, self.onRightMouse)
        self.hasUI = True
        return self.panel


    def updateUI(self):
        if not self.hasUI:
            # No UI to update.
            return
        # If there is no local amplifierMode
        mode = self.settings.get('amplifierMode', None)
        if not mode:
            try:
                # try to read it from the hardware
                mode = self.object.get_settings()['amplifierMode']
            except:
                mode = None

        # If we succeeded in retrieving a mode ...
        if mode:
            # fetch the mode description ...
            modeString = mode['label']
            # and figure out of it uses EM.
            modeIsEM = mode['amplifier'] == 0
        else:
            # Otherwise, show that we have no mode description ...
            modeString = 'not set'
            # and assume no EM.
            modeIsEM = False

        # Light up the mode button if the camera is active.
        if self.enabled:
            self.modeButton.setActive(True)
        else:
            self.modeButton.setActive(False)

        # Light up the gain button if camera is active and mode uses EM.
        if modeIsEM and self.enabled:
            self.gainButton.setActive(True)
        else:
            self.gainButton.setActive(False)

        # Labels must be set after setActive call, or the original
        # label persists.
        self.modeButton.SetLabel('Mode:\n%s' % modeString)
        self.gainButton.SetLabel('EM Gain:\n%d' % self.settings['EMGain'])


class UniversalCameraManager(camera.CameraManager):
    _CAMERA_CLASS = UniversalCameraDevice
