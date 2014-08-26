""" This module makes Andor camera devices available to Cockpit.

Mick Phillips, University of Oxford, 2014.
Historically, a single CameraDevice was used to address multiple
cameras, using a number of dictionaries to map the camera name to
its settings and methods.  Here, instead I have used a single
CameraManager to keep track of one or more CameraDevices, which
means that inheritance can be used for different camera types."""

import device
import events
import gui.guiUtils
import gui.toggleButton
import handlers.camera
import util.connection
import util.threads

import collections
import decimal
import numpy
import threading
import time
import wx

from config import CAMERAS

CLASS_NAME = 'CameraManager'
SUPPORTED_CAMERAS = ['ixon', 'ixon_plus', 'ixon_ultra']

class CameraManager(device.Device):
    """ CameraManager: a class to manage camera devices."""
    def __init__(self):
        self.cameras = []
        for name, camConfig in CAMERAS.iteritems():
            cameratype = camConfig.get('model', '')
            if cameratype in SUPPORTED_CAMERAS:
                self.cameras.append(AndorCameraDevice(camConfig))


    def getHandlers(self):
        result = []
        for camera in self.cameras:
            result.extend(camera.getHandlers)
        return result



class AndorCameraDevice(device.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, camConfig):
        self.config = camConfig
        self.connection = util.connection.Connection(
                'pyroCam',
                self.config.get('ipAddress'),
                self.config.get('port'))
        self.imageSizes = ['Full', '512x256', '512x128']


    def performSubscriptions(self):
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)


    def getHandlers(self):
        result = []
        result.append(handlers.camera.CameraHandler(
                "%s" % self.config.get('name'), "iXon camera", 
                {'setEnabled': self.enableCamera, 
                    'getImageSize': self.getImageSize, 
                    'getTimeBetweenExposures': self.getTimeBetweenExposures, 
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize, 
                    'getSavefileInfo': self.getSavefileInfo},
                handlers.camera.TRIGGER_AFTER))
        return result


    def enableCamera(self, shouldEnable):
        pass


    def getExposureTime(self, isExact):
        pass


    def getImageSize(self):
        pass


    def getImageSizes(self):
        return self.imageSizes


    def getSavefileInfo(self):
        pass


    def getTimeBetweenExposures(self):
        pass


    def prepareForExperiment(self, experiment):
        pass


    def receiveData(self, name, action, *args):
        if action == 'new image':
            (image, timestamp) = args
            self.orient(image)
            events.publish('new image %s' % name, image, timestamp)


    def setExposureTime(self, exposureTime):
        pass


    def setImageSize(self, imageSize):
        pass