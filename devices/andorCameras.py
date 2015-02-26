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
DEFAULT_TRIGGER = 'TRIGGER_BEFORE'
COLOUR = {'grey': (170, 170, 170),
          'green': (32, 128, 32),
        }


# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION) = range(3)


class AndorCameraDevice(camera.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, camConfig):
        # camConfig is a dict with containing configuration parameters.
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
        self.cached_settings={}
        self.settings = {}
        self.settings['exposureTime'] = 0.001
        self.settings['isWaterCooled'] = False
        self.settings['targetTemperature'] = -40
        self.settings['EMGain'] = 0
        self.settings['amplifierMode'] = None
        self.settings['baseTransform'] = camConfig.get('baseTransform') or (0, 0, 0)
        self.settings['pathTransform'] = (0, 0, 0)
        self.enabled = False


    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.settings.update(self.cached_settings)
            self.object.enable(self.settings)


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)
        events.subscribe('objective change',
                self.onObjectiveChange)


    def onObjectiveChange(self, name, pixelSize, transform):
        self.settings.update({'pathTransform': transform})
        # Apply the change now if the camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)
    

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
        """Enable the hardware."""
        trigger = self.config.get('trigger', DEFAULT_TRIGGER)
        if shouldEnable:
            # Connect and set up callback.
            try:
                self.connection.connect(lambda *args: self.receiveData(*args))
            except Exception as e:
                print e
            else:
                self.object = self.connection.connection
                thread = gui.guiUtils.WaitMessageDialog("Connecting to %s" % name,
                                                        "Connecting ...", 0.5)
                thread.start()

                originalTimeout = self.object._pyroTimeout
                self.object._pyroTimeout = 60
                self.settings['frameTransfer'] = False
                self.object.enable(self.settings)
                # Wait for camera to show it is enabled.
                while not self.object.is_enabled():
                    time.sleep(1)
                self.object._pyroTimeout = originalTimeout

                # Update our settings with the real settings.
                self.settings.update(self.object.get_settings())

                # Get the list of available amplifier modes.
                self.amplifierModes = self.object.get_amplifier_modes()

                thread.shouldStop = True
                self.enabled = True
        else:
            self.enabled = False
            self.object.disable()
            self.connection.disconnect()

        # Finally, udate our UI buttons.
        self.updateUI()


    def getExposureTime(self, name, isExact):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        return self.object.get_exposure_time() * 1000.0


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
        self.settings['frameTransfer'] = True
        self.object.abort()
        self.object.enable(self.settings)
        #self.setExposureTime(name, 0)
        # Since we'll be in frame-transfer mode, we'll be accumulating light
        # until the next external trigger. This causes a lot of background in
        # the first image. So we'll trigger the first image immediately before
        # starting the experiment (or as close-to as possible) and discard it.
        #self.object.skip_images(next=1)


    def receiveData(self, action, *args):
        """This function is called when data is received from the hardware."""
        print 'receiveData received %s' % action
        if action == 'new image':
            (image, timestamp) = args
            self.orient(image)
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


    def setAmplifierMode(self, mode):
        self.settings.update({'amplifierMode': mode})
        # Apply the change right now if camera is enabled.
        if self.enabled:
            self.object.update_settings(self.settings)
        self.updateUI()


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetBackgroundColour(COLOUR['grey'])
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self.panel, -1,
                              self.config['label'],
                              size=(128, 24),
                              style=wx.ALIGN_CENTER)
        label.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.VERTICAL)

        self.modeButton = gui.toggleButton.ToggleButton(
                label="Mode:\n%s" % 'mode_desc',
                parent=self.panel, size=(128,48))
        self.modeButton.Bind(wx.EVT_LEFT_DOWN, self.onModeButton)
        rowSizer.Add(self.modeButton)

        self.gainButton = gui.toggleButton.ToggleButton(
                label="EM Gain\n%d" % self.settings['EMGain'],
                parent=self.panel, size=(128, 48))
        self.gainButton.Bind(wx.EVT_LEFT_DOWN, self.onGainButton)
        rowSizer.Add(self.gainButton)
        
        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def updateUI(self):
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
            modeString = '???'
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


class CameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
