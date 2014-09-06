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

import device
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


class AndorCameraDevice(device.CameraDevice):
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
        ## Initial values should be read in from the config file.
        self.settings = {}
        self.settings['exposureTime'] = 100
        self.settings['isWaterCooled'] = False
        self.settings['targetTemperature'] = -40        


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
                raise
            else:
                self.object = self.connection.connection
                thread = gui.guiUtils.WaitMessageDialog(
                    "Connecting to %s" % name,
                    "Connecting ...",
                    0.5)
                thread.start()
                try:
                    self.object.enable(self.settings)
                    while not self.object.enabled:
                        time.sleep(1)
                except:
                    raise
                finally:
                    thread.shouldStop = True


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


class CameraManager(device.CameraManager):
    _CAMERA_CLASS = AndorCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
