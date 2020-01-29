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


""" This module makes software-driven cameras available to cockpit.
"""
from . import camera
from cockpit import events
import cockpit.handlers.camera
import numpy as np
import cockpit.util.listener
import Pyro4

SUPPORTED_CAMERAS = ['flycap2','picam']


class SoftCamera(camera.CameraDevice):
    """A class for software-driven cameras."""
    def __init__(self, name, camConfig):
        super(SoftCamera, self).__init__(name, camConfig)
        self.config = camConfig
        self.enabled = False
        ## Pyro proxy (formerly a copy of self.connection.connection).
        self.remote =  Pyro4.Proxy('PYRO:%s@%s:%d' % ('pyroCam',
                                                      camConfig.get('ipAddress'),
                                                      camConfig.get('port')))
        self.listener = cockpit.util.listener.Listener(self.remote,
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
        result = cockpit.handlers.camera.CameraHandler(
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
                cockpit.handlers.camera.TRIGGER_SOFT)
        self.handler = result
        return result


    def enableCamera(self, name, shouldEnable):
        if shouldEnable:
            self.enabled = True
            self.remote.enableCamera()
            self.listener.connect()
        else:
            self.remote.disableCamera()
            self.listener.disconnect()
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
            transform = self.transform
            if transform.rot90:
                image = np.rot90(image, transform.rot90)
            if transform.flip_h:
                image = np.fliplr(image)
            if transform.flip_v:
                image = np.flipud(image)
            events.publish('new image %s' % self.name, image, timestamp)


    def setExposureTime(self, name, exposureTime):
        return self.remote.setExposureTime(exposureTime)


    def setImageSize(self, name, imageSize):
        return self.remote.setImageSize(imageSize)

