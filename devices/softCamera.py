#!/usr/bin/python
# -*- coding: UTF8   -*-
""" This module makes software-driven cameras available to cockpit.

Copyright 2015 Mick Phillips (mick.phillips at gmail dot com)

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
"""
import camera
import events
import handlers.camera
import util.listener
import Pyro4
from config import CAMERAS

CLASS_NAME = 'SoftCameraManager'
SUPPORTED_CAMERAS = ['flycap2']

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION, TRIGGER_SOFTWARE) = range(4)


class SoftCameraDevice(camera.CameraDevice):
    """A class for software-driven cameras."""
    def __init__(self, camConfig):
        super(SoftCameraDevice, self).__init__(camConfig)
        self.config = camConfig
        self.enabled = False
        ## Pyro proxy (formerly a copy of self.connection.connection).
        self.remote =  Pyro4.Proxy('PYRO:%s@%s:%d' % ('pyroCam',
                                                      camConfig.get('ipAddress'),
                                                      camConfig.get('port')))
        self.listener = util.listener.Listener(self.remote,
                                               lambda *args: self.receiveData(*args))


    def cleanupAfterExperiment(self):
        pass


    def performSubscriptions(self):
        events.subscribe("dummy take image", self.onDummyImage)


    def onDummyImage(self, camera=None):
        if self.enabled:
            self.remote.softTrigger()


    def getHandlers(self):
        """Return camera handlers."""
        remote = self.remote
        result = handlers.camera.CameraHandler(
                "%s" % self.config.get('label'), "soft camera",
                {'setEnabled': self.enableCamera,
                    'getImageSize': self.getImageSize,
                    'getTimeBetweenExposures': self.getTimeBetweenExposures,
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize,
                    'getSavefileInfo': self.getSavefileInfo,
                    },
                TRIGGER_SOFTWARE)
        self.handler = result
        return result


    def enableCamera(self, name, shouldEnable):
        if shouldEnable:
            self.enabled = True
            self.remote.enableCamera()
            self.listener.connect()
        else:
            self.enabled = False


    def getExposureTime(self, name, isExact=False):
        return self.remote.getExposureTime(isExact)


    def getImageSize(self, name):
        return self.remote.getImageSize()


    def getImageSizes(self, name):
        return self.remote.getImageSizes()


    def getSavefileInfo(self, name):
        return 'Soft camera image'


    def getTimeBetweenExposures(self, name, isExact=False):
        return self.remote.getTimeBetweenExposures(isExact)


    def prepareForExperiment(self, name, experiment):
        pass


    def receiveData(self, action, *args):
        """This function is called when data is received from the hardware."""
        # print 'receiveData received %s' % action
        if action == 'new image':
            (image, timestamp) = args
            events.publish('new image %s' % self.name, image, timestamp)


    def setExposureTime(self, name, exposureTime):
        return self.remote.setExposureTime(exposureTime)


    def setImageSize(self, name, imageSize):
        return self.remote.setImageSize(imageSize)


class SoftCameraManager(camera.CameraManager):
    _CAMERA_CLASS = SoftCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
