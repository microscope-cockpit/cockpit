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

class CameraManager(device.Device):
    """A class to manage camera devices in cockpit."""
    def __init__(self):
        self.cameras = []
        for name, camConfig in CAMERAS.iteritems():
            cameratype = camConfig.get('model', '')
            if cameratype in SUPPORTED_CAMERAS:
                self.cameras.append(AndorCameraDevice(camConfig))
        if len(self.cameras) > 0:
            self.isActive = True
        self.priority = 100


    def getHandlers(self):
        """Aggregate and return handlers from managed cameras."""
        result = []
        for camera in self.cameras:
            result.append(camera.getHandlers())
        return result


class AndorCameraDevice(device.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, camConfig):
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
            self.connection.connect(
                lambda *args: self.receiveData(*args))
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
        pass


    def getImageSize(self, name):
        pass


    def getImageSizes(self, name):
        return self.imageSizes


    def getSavefileInfo(self, name):
        pass


    def getTimeBetweenExposures(self, name, isExact):
        pass


    def prepareForExperiment(self, name, experiment):
        pass


    def receiveData(self, name, action, *args):
        if action == 'new image':
            (image, timestamp) = args
            self.orient(image)
            events.publish('new image %s' % self.name, image, timestamp)


    def setExposureTime(self, name, exposureTime):
        self.settings['exposureTime'] = exposureTime
        self.set_exposure_time(exposureTime)


    def setImageSize(self, name, imageSize):
        pass