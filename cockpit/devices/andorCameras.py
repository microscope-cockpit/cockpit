#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
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


""" This module makes Andor EMCCD camera devices available to Cockpit.

Historically, a single CameraDevice was used to address multiple
cameras, using a number of dictionaries to map the camera name to
its settings and methods.  Here, instead I have used a single
CameraManager to keep track of one or more CameraDevices, which
means that inheritance can be used for different camera types.

All the handler functions are called with (self, name, *args...).
Since we make calls to instance methods here, we don't need 'name',
but it is left in the call so that we can continue to use camera
modules that rely on dictionaries.

Cockpit uses lowerCamelCase function names.
Functions names as lower_case are remote camera object methods.

Sample config entry:
  [some name]
  type: AndorCameraDevice
  uri: PYRO:pyroCam@192.168.1.2:7777
  triggerSource: trigsource
  triggerLine: 1
  transform: (0,0,1)

  [trigsource]
  type: ExecutorDevice
  ...


"""

import collections
import decimal
import threading
import time
import wx

from . import camera
import depot
import events
import handlers.camera
import gui.device
import gui.guiUtils
import gui.toggleButton
import Pyro4
import util.listener
import util.threads

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION) = range(3)

TriggerMode = collections.namedtuple('TriggerMode', 
        ['label',
         'frameTransfer',
         'fastTrigger',
         'cameraTrigger',
         'cockpitTrigger'])

TRIGGER_MODES = [
    TriggerMode('clean, no FT', False, False, 1, TRIGGER_BEFORE),
    TriggerMode('fast, no FT', False, True, 1, TRIGGER_BEFORE),
    TriggerMode('clean, with FT', True, False, 1, TRIGGER_AFTER),
    TriggerMode('fast, with FT', True, True, 1, TRIGGER_AFTER),
    TriggerMode('bulb', False, False, 7, TRIGGER_DURATION)
]


class AndorCameraDevice(camera.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, name, config):
        super(AndorCameraDevice, self).__init__(name, config)
        ## Pyro proxy (formerly a copy of self.connection.connection).
        self.proxy =  Pyro4.Proxy(self.uri)
        ## A listner (formerly self.connection).
        self.listener = util.listener.Listener(self.proxy,
                                               lambda *args: self.receiveData(*args))
        self.imageSizes = ['Full', '512x256', '512x128']
        try:
            self.amplifierModes = self.proxy.get_amplifier_modes()
        except:
            self.amplifierModes = None
        ## Initial values should be read in from the config file.
        self.cached_settings={}
        self.settings['exposureTime'] = 0.001
        # Has water cooling? Default to False to ensure fan is active.
        self.settings['isWaterCooled'] = False
        self.settings['targetTemperature'] = -40
        self.settings['EMGain'] = 0
        self.settings['amplifierMode'] = None
        self.settings['triggerMode'] = 1
        self.lastTemperature = None
        self.experimentTriggerMode = TRIGGER_MODES[0]
        self.interactiveTrigger = TRIGGER_DURATION
        self.enabled = False
        self.handler = None
        self.hasUI = False
        # A thread to publish status updates.
        self.statusThread = threading.Thread(target=self.updateStatus)
        self.statusThread.Daemon = True
        self.statusThread.start()


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.settings.update(self.cached_settings)
            self.proxy.enable(self.settings)
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
            self.proxy.update_settings(self.settings)
    

    def getHandlers(self):
        """Return camera handlers."""
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None

        """Return camera handlers."""
        result = handlers.camera.CameraHandler(
                "%s" % self.name, "iXon camera",
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
                self.interactiveTrigger,
                trighandler,
                trigline
        )
        self.handler = result
        self.handler.addListener(self)
        return [result]


    def onEnabledEvent(self, evt=None):
        if self.enabled:
            self.handler.exposureMode = self.interactiveTrigger
            self.listener.connect()


    def enableCamera(self, name, shouldEnable):
        """Enable the hardware."""
        if not shouldEnable:
            # Disable the camera, if it is enabled.
            if self.enabled:
                self.enabled = False
                self.proxy.disable()
                self.proxy.make_safe()
                self.listener.disconnect()
                self.updateUI()
                return self.enabled

        # Enable the camera
        if self.enabled:
            # Nothing to do.
            return self.enabled

        # We don't want fast triggers or frame transfer outside of experiments.
        self.settings['frameTransfer'] = False
        self.settings['fastTrigger'] = False

        originalTimeout = self.proxy._pyroTimeout
        try:
            self.proxy._pyroTimeout = 60
            self.proxy.enable(self.settings)
            self.proxy._pyroTimeout = originalTimeout
        except Exception as e:
            print (e)
        else:
            # Wait for camera to show it is enabled.
            while not self.proxy.is_enabled():
                time.sleep(1)
            self.enabled = True
            # Connect the listener to receive data.
            self.listener.connect()
            # Update our settings with the real settings.
            self.settings.update(self.proxy.get_settings())
            # Get the list of available amplifier modes.
            self.amplifierModes = self.proxy.get_amplifier_modes()
        # Update the UI.
        self.updateUI()
        return self.enabled


    def getExposureTime(self, name, isExact):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        t = self.proxy.get_exposure_time()
        if isExact:
            return decimal.Decimal(t) * (decimal.Decimal(1000.0))
        else:
            return t * 1000.0


    def getImageSize(self, name):
        """Read the image size from the camera."""
        return self.proxy.get_image_size()


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
        t = self.proxy.get_min_time_between_exposures() * 1000.0
        if isExact:
            result = decimal.Decimal(t)
        else:
            result = t
        return result


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)
        self.proxy.abort()
        self.settings['frameTransfer'] = self.experimentTriggerMode.frameTransfer
        self.settings['fastTrigger'] = self.experimentTriggerMode.fastTrigger
        self.settings['triggerMode'] = self.experimentTriggerMode.cameraTrigger
        try:
            self.proxy.enable(self.settings)
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
            self.proxy.update_settings(self.settings)


    def setImageSize(self, name, imageSize):
        pass


    ### UI stuff ###
    def onGainButton(self, event=None):
        menu = wx.Menu()
        menuID = 1
        for value in range (0, 255, 10):
            menu.Append(menuID, str(value))
            self.panel.Bind(wx.EVT_MENU,  lambda event, value=value: self.setGain(value), id= menuID)
            menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def setGain(self, value):
        self.settings.update({'EMGain': value})
        # Apply the change now if the camera is enabled.
        if self.enabled:
            self.proxy.update_settings(self.settings)
        self.updateUI()


    def onModeButton(self, event=None):
        menu = wx.Menu()
        if not self.amplifierModes:
            # Camera not enabled yet.
            menu.Append(0, str('No modes known - camera never enabled.'))
            self.panel.Bind(wx.EVT_MENU,  None, id= 0)
        else:
            menuID = 0
            for mode in self.amplifierModes:
                menu.Append(menuID, mode['label'])
                self.panel.Bind(wx.EVT_MENU,
                                lambda event, m=mode: self.setAmplifierMode(m),
                                id=menuID)
                menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def onRightMouse(self, event=None):
        """Present a thermal management menu on right click."""
        menu = wx.Menu()
        menu.SetTitle('Thermal management')

        # Check control to indicate/set water cooling availability.
        menu.AppendCheckItem(0, 'water cooling')
        menu.Check(0, self.settings.get('isWaterCooled', False))
        self.panel.Bind(wx.EVT_MENU,  lambda event: self.toggleWaterCooling(), id= 0)

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
            self.panel.Bind(wx.EVT_MENU,  lambda event, target=t: self.setTargetTemperature(target), id= itemID)
            itemID += 1

        menu.AppendSubMenu(tMenu, 'sensor set point')

        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def onTrigButton(self, event=None):
        menu = wx.Menu()
        menuID = 0
        for mode in TRIGGER_MODES:
            menu.Append(menuID, mode.label)
            self.panel.Bind(wx.EVT_MENU,
                            lambda event, m=mode: self.setExperimentTriggerMode(m),
                            id=menuID)
            menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def setExperimentTriggerMode(self, mode):
        self.experimentTriggerMode = mode
        self.trigButton.SetLabel('exp. trigger:\n%s' % mode.label)


    def setAmplifierMode(self, mode):
        self.settings.update({'amplifierMode': mode})
        # Apply the change right now if camera is enabled.
        if self.enabled:
            self.proxy.update_settings(self.settings)
        self.updateUI()


    def setTargetTemperature(self, temperature):
        self.settings.update({'targetTemperature': temperature})
        self.proxy.update_settings({'targetTemperature': temperature})


    def toggleWaterCooling(self):
        newSetting = not self.settings.get('isWaterCooled')
        self.settings.update({'isWaterCooled': newSetting})
        self.proxy.update_settings({'isWaterCooled': newSetting})


    def updateStatus(self):
        """Runs in a separate thread publish status updates."""
        updatePeriod = 2
        temperature = None
        while True:
            if self.proxy:
                try:
                    temperature = self.proxy.get_temperature()
                except:
                    ## There is a communication issue. It's not this thread's
                    # job to fix it. Set temperature to None to avoid bogus
                    # data.
                    temperature = None
            self.lastTemperature = temperature
            events.publish("status update",
                           self.name,
                           {'temperature': temperature,})
            time.sleep(updatePeriod)


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
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
        self.panel.Bind(wx.EVT_CONTEXT_MENU, self.onRightMouse)
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
                mode = self.proxy.get_settings()['amplifierMode']
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
