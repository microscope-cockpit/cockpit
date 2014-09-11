""" This module makes Andor camera devices available to Cockpit.

Mick Phillips, University of Oxford, 2014.
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
import gui.guiUtils
import gui.toggleButton
import util.connection
import util.threads

from config import CAMERAS

CLASS_NAME = 'CameraManager'
SUPPORTED_CAMERAS = ['ixon', 'ixon_plus', 'ixon_ultra']
DEFAULT_TRIGGER = 'TRIGGER_AFTER'

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION) = range(3)


class AndorCameraDevice(camera.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, camConfig):
        super(AndorCameraDevice, self).__init__(camConfig)
        self.config = camConfig
        self.connection = util.connection.Connection(
                'pyroCam',
                self.config.get('ipAddress'),
                self.config.get('port'))
        self.object = None
        self.imageSizes = ['Full', '512x256', '512x128']
        self.amplifierModes = None
        ## Initial values should be read in from the config file.
        self.settings = {}
        self.settings['exposureTime'] = 100
        self.settings['isWaterCooled'] = False
        self.settings['targetTemperature'] = -40  
        self.settings['EMGain'] = 0
        self.settings['amplifierMode'] = None

    def cleanupAfterExperiment(self):
        # Restore settings as they were prior to experiment.
        self.object.enable(self.settings)


    def performSubscriptions(self):
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)


    def getHandlers(self):
        """Return camera handlers."""
        trigger = globals().get(
                # find in config
                self.config.get('trigger', ''), 
                # or default to
                DEFAULT_TRIGGER)

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
                    'getSavefileInfo': self.getSavefileInfo},
                trigger)
        return result


    def enableCamera(self, name, shouldEnable):
        trigger = self.config.get('trigger', DEFAULT_TRIGGER)
        if shouldEnable:
            # Connect and set up callback.
            try:
                self.connection.connect(
                    lambda *args: self.receiveData(*args))
            except:
                raise Exception('Could not connect to camera %s' % name)
            else:
                self.object = self.connection.connection
                thread = gui.guiUtils.WaitMessageDialog(
                    "Connecting to %s" % name,
                    "Connecting ...",
                    0.5)
                thread.start()
                try:
                    self.object.enable(self.settings)
                    # Wait for camera to show it is enabled.
                    while not self.object.enabled:
                        time.sleep(1)
                    # Update our settings with the real settings. 
                    remote_settings = self.object.get_settings()
                    self.settings.update(remote_settings)
                    
                    # Get the list of available amplifier modes.
                    self.amplifierModes = self.object.get_amplifier_modes()

                    # Update our UI buttons.
                    self.modeButton.Enable()
                    self.modeButton.SetLabel('Mode:\n%s' % 
                            self.settings['amplifierMode']['label'])
                    if self.settings['amplifierMode']['amplifier'] == 0:
                        self.gainButton.Enable()
                        self.gainButton.SetLabel('EM Gain:\n%d' %
                                self.settings['EMGain'])

                    # Update camera buttons
                    self.modeButton.Enable()
                    if not self.settings.get('amplifierMode', None):
                        try:
                            mode = self.object.get_settings()['amplifierMode']
                        except:
                            mode = None

                        if mode:
                            self.settings.update({'amplifierMode', mode})
                            modeText = mode['label']
                        else:
                            modeText = '???'
                        self.modeButton.SetLabel('Mode:\n%s' % modeText)
                except:
                    raise
                finally:
                    thread.shouldStop = True
        else:
            self.gainButton.Disable()
            self.modeButton.Disable()


    def getExposureTime(self, name, isExact):
        # Camera uses times in s; cockpit uses ms.
        return self.object.get_exposure_time() * 1000.0


    def getImageSize(self, name):
        return self.object.get_image_size()


    def getImageSizes(self, name):
        return self.imageSizes


    def getSavefileInfo(self, name):
        pass


    def getTimeBetweenExposures(self, name, isExact):
        ## Get the amount of time that must pass after stopping one exposure
        # before another can be started, in milliseconds.
        # Camera uses time in s; cockpit uses ms.
        return self.object.get_min_time_between_exposures() * 1000.0


    def prepareForExperiment(self, name, experiment):
        pass


    def receiveData(self, name, action, *args):
        if action == 'new image':
            (image, timestamp) = args
            self.orient(image)
            events.publish('new image %s' % self.name, image, timestamp)


    def setExposureTime(self, name, exposureTime):
        # Camera uses times in s; cockpit uses ms.
        self.settings['exposureTime'] = exposureTime
        self.set_exposure_time(exposureTime / 1000.0)


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
        self.settings['EMGain'] = value
        self.object.update_settings(self.settings)
        self.gainButton.SetLabel('EM Gain\n%d' % value)


    def onModeButton(self, event=None):
        menu = wx.Menu()
        if not self.amplifierModes:
            # Camera not enabled yet.
            menu.Append(0, str('Camera not enabled.'))
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


    def setAmplifierMode(self, mode):
        self.object.set_amplifier_mode(mode)
        if mode.get('amplifier'):
            self.gainButton.SetLabel('EM Gain\noff')
            self.gainButton.Disable()
        else:
            self.gainButton.SetLabel('EM Gain\n%d' % self.settings['EMGain'])
            self.gainButton.Enable()
        self.modeButton.SetLabel('Mode:\n%s' % mode['label'])
        self.settings.update({'amplifierMode': mode})


    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetBackgroundColour((170, 170, 170))
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self.panel, -1,
                              self.config['label'], 
                              size=(128, 24),
                              style=wx.ALIGN_CENTER)
        label.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.VERTICAL)
        self.gainButton = gui.toggleButton.ToggleButton(
                label="EM Gain\n%d" % self.settings['EMGain'],
                parent=self.panel, size=(128, 48))
        self.gainButton.Bind(wx.EVT_LEFT_DOWN, self.onGainButton)
        rowSizer.Add(self.gainButton)
        
        self.modeButton = gui.toggleButton.ToggleButton(
                label="Mode:\n%s" % 'mode_desc',
                parent=self.panel, size=(128,48))
        self.modeButton.Bind(wx.EVT_LEFT_DOWN, self.onModeButton)
        rowSizer.Add(self.modeButton)
        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        # These buttons are enabled when the camera is enabled.
        self.modeButton.Disable()
        self.gainButton.Disable()
        return self.panel


class CameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
