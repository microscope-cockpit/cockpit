# coding: utf-8
""" This module makes Andor EMCCD camera devices available to Cockpit.

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================

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
"""

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

CLASS_NAME = 'AndorCameraManager'
SUPPORTED_CAMERAS = ['ixon', 'ixon_plus', 'ixon_ultra']

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
    def __init__(self, camConfig):
        # camConfig is a dict with containing configuration parameters.
        super(AndorCameraDevice, self).__init__(camConfig)
        self.config = camConfig
        ## Pyro proxy (formerly a copy of self.connection.connection).
        self.object =  Pyro4.Proxy('PYRO:%s@%s:%d' % ('pyroCam',
                                                      camConfig.get('ipAddress'),
                                                      camConfig.get('port')))
        ## A listner (formerly self.connection).
        self.listener = util.listener.Listener(self.object, 
                                               lambda *args: self.receiveData(*args))
        self.imageSizes = ['Full', '512x256', '512x128']
        try:
            self.amplifierModes = self.object.get_amplifier_modes()
        except:
            self.amplifierModes = None
        ## Initial values should be read in from the config file.
        self.cached_settings={}
        self.settings = {}
        self.settings['exposureTime'] = 0.001
        # Has water cooling? Default to False to ensure fan is active.
        self.settings['isWaterCooled'] = False
        self.settings['targetTemperature'] = -40
        self.settings['EMGain'] = 0
        self.settings['amplifierMode'] = None
        self.settings['baseTransform'] = camConfig.get('baseTransform') or (0, 0, 0)
        self.settings['pathTransform'] = (0, 0, 0)
        self.settings['triggerMode'] = 1
        self.lastTemperature = None
        self.experimentTriggerMode = TRIGGER_MODES[0]
        self.interactiveTrigger = TRIGGER_BEFORE
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
            self.object.enable(self.settings)
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
                return self.enabled

        # Enable the camera
        if self.enabled:
            # Nothing to do.
            return self.enabled

        # We don't want fast triggers or frame transfer outside of experiments.
        self.settings['frameTransfer'] = False
        self.settings['fastTrigger'] = False

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
            # Get the list of available amplifier modes.
            self.amplifierModes = self.object.get_amplifier_modes()
        # Update the UI.
        self.updateUI()
        return self.enabled


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


    def updateStatus(self):
        """Runs in a separate thread publish status updates."""
        updatePeriod = 2
        temperature = None
        while True:
            if self.object:
                try:
                    temperature = self.object.get_temperature()
                except:
                    ## There is a communication issue. It's not this thread's
                    # job to fix it. Set temperature to None to avoid bogus
                    # data.
                    temperature = None
            self.lastTemperature = temperature
            events.publish("status update",
                           self.config.get('label', 'unidentifiedCamera'),
                           {'temperature': temperature,})
            time.sleep(updatePeriod)


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


class AndorCameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
