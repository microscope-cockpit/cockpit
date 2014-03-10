import depot
import device
import events
import handlers.camera
import util.connection

import decimal
import numpy
import Pyro4
import threading
import time

CLASS_NAME = 'CameraDevice'

## Valid trigger modes for the cameras.
(TRIGGER_INTERNAL, TRIGGER_EXTERNAL, TRIGGER_EXTERNAL_EXPOSURE) = range(3)



class CameraDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Maps camera names to Connection instances.
        self.nameToConnection = {}
        ## Maps camera names to their Handlers.
        self.nameToHandler = {}
        ## Maps camera names to the last exposure times we set for them.
        self.nameToExposureTime = {}
        ## Maps camera names to their minimum possible exposure times.
        self.nameToMinExposureTime = {}
        ## Cached copies of our time-between-exposure values.
        self.nameToTimeBetweenExposures = {}
        ## List of valid image size strings.
        self.imageSizes = ['Full (2560x2160)', 'Quarter (1392x1040)',
                '528x512', '240x256', '144x128']
        ## Current trigger mode for cameras.
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE

        events.subscribe('experiment complete', self.onExperimentComplete)


    def getHandlers(self):
        result = []
        for name, ipAddress, port in [('Zyla', '10.0.0.2', 7000)]:
            result.append(handlers.camera.CameraHandler(
                name, "sCMOS camera", 
                {'setEnabled': self.enableCamera, 
                    'getImageSize': self.getImageSize, 
                    'getTimeBetweenExposures': self.getTimeBetweenExposures, 
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize,
                    'getMinExposureTime': self.getMinExposureTime},
                handlers.camera.TRIGGER_BEFORE))
            self.nameToConnection[name] = util.connection.Connection(
                    'Andorcam', ipAddress, port,
                    localIp = '10.0.0.1')
            self.nameToHandler[name] = result[-1]
        return result


    ## Handle a camera connecting or disconnecting.
    def enableCamera(self, name, isOn):
        if isOn:
            self.nameToConnection[name].connect(lambda *args: self.receiveData(name, *args))
            connection = self.nameToConnection[name].connection
            # Set 528x512 image size.
            connection.setCrop(2)
            # Switch to external exposure mode.
            connection.setTrigger(self.curTriggerMode)
        else:
            self.nameToConnection[name].disconnect()
        self.invalidateCaches(name)


    ## Clear our caches for a given camera, so that they must be reacquired.
    def invalidateCaches(self, name):
        for cache in [self.nameToExposureTime, self.nameToMinExposureTime,
                self.nameToTimeBetweenExposures]:
            if name in cache:
                del cache[name]
        # Reacquire values for the min exposure time now, since otherwise
        # we risk trying to get them in the preparation for an experiment,
        # at which point the camera's state has been changed; this makes
        # the experiment not work.
        self.getMinExposureTime(name)


    ## Receive data from a camera. 
    def receiveData(self, name, action, *args):
        if action == 'new image':
            (image, timestamp) = args
            events.publish("new image %s" % name, image, timestamp)


    ## Get the size of the image this camera generates.
    def getImageSize(self, name):
        return self.nameToConnection[name].connection.getImageShape()


    ## Get the time between exposures -- i.e. the time spent reading
    # out the sensor. Result is in milliseconds.
    def getTimeBetweenExposures(self, name, isExact = False):
        if name in self.nameToTimeBetweenExposures:
            # Use the cached value
            val = self.nameToTimeBetweenExposures[name]
        else:
            val = self.nameToConnection[name].connection.getReadoutTime() * 1000 + .05
            self.nameToTimeBetweenExposures[name] = val
        if isExact:
            val = decimal.Decimal(val)
        return val


    ## Change the exposure time.
    def setExposureTime(self, name, newTime):
        # Input may be a decimal.Decimal object, but we can only operate on
        # floats.
        newTime = float(newTime)
        # Enforce nonzero exposure times, while changing from milliseconds
        # to seconds.
        newTime = max(.001, newTime / 1000)
        if (name in self.nameToExposureTime and
                abs(self.nameToExposureTime[name] - newTime) < .001):
            # We're already there; don't bother.
            return
        connection = self.nameToConnection[name].connection
        connection.setExposureTime(newTime)
        connection.setTrigger(self.curTriggerMode)
        self.nameToExposureTime[name] = newTime


    ## Get the exposure time for this camera, in milliseconds.
    def getExposureTime(self, name, isExact = False):
        val = self.nameToConnection[name].connection.getExposureTime() * 1000
        if isExact:
            return decimal.Decimal(val)
        return val


    ## Get the minimum exposure time the camera is capable of performing.
    # Unfortunately there's no API call for this, so we have to derive it
    # by setting an absurdly low time, reseting the trigger mode,
    # and then checking the actual exposure time.
    # Because of the extra actions, getting this value is nontrivial, so
    # we cache it.
    def getMinExposureTime(self, name):
        if name in self.nameToMinExposureTime:
            return self.nameToMinExposureTime[name]
        connection = self.nameToConnection[name].connection
        if connection is None:
            # Can't do anything.
            return
        curExposureTime = connection.getExposureTime()
        connection.setExposureTime(.00001)
        connection.setTrigger(self.curTriggerMode)
        # Convert from seconds to milliseconds. 
        result = connection.getExposureTime() * 1000
        connection.setExposureTime(curExposureTime)
        self.nameToMinExposureTime[name] = result
        return result


    ## Get a list of valid image sizes for the camera.
    def getImageSizes(self, name):
        return self.imageSizes


    ## Set the image size for the camera.
    def setImageSize(self, name, size):
        connection = self.nameToConnection[name].connection
        connection.setCrop(self.imageSizes.index(size))
        connection.setTrigger(self.curTriggerMode)
        # Readout time has changed.
        self.invalidateCaches(name)


    ## Get the camera ready for an experiment. 
    def prepareForExperiment(self, name, experiment):
        connection = self.nameToConnection[name].connection
        handler = self.nameToHandler[name]
        exposureTime = experiment.getExposureTimeForCamera(handler)
        self.setExposureTime(name, exposureTime)
        connection.setTrigger(TRIGGER_EXTERNAL)
        self.curTriggerMode = TRIGGER_EXTERNAL


    ## Handle an experiment finishing; switch our cameras back to
    # external exposure mode.
    def onExperimentComplete(self):
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE
        for connection in self.nameToConnection.values():
            if connection.connection is not None:
                # Camera is connected.
                connection.connection.setTrigger(self.curTriggerMode)

