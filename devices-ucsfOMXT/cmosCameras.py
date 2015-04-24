import camera
import depot
import events
import handlers.camera
import util.connection
import util.threads

import decimal
import numpy
import Pyro4
import Queue
import threading
import time

from config import config, CAMERAS

CLASS_NAME = 'CameraManager'
SUPPORTED_CAMERAS = ['neo', 'zyla']


## Valid trigger modes for the cameras.
(TRIGGER_INTERNAL, TRIGGER_EXTERNAL, TRIGGER_EXTERNAL_EXPOSURE) = range(3)



class AndorCMOSCameraDevice(camera.CameraDevice):
    def __init__(self, camConfig):
        # camConfig is a dict containing configuration parameters.
        super(AndorCMOSCameraDevice, self).__init__(camConfig)
        self.config = camConfig
        # Should this IP address be gotten through handlers/server.py instead?
        # Doing so would require adding a function to handlers/server.py to
        # return the IP adress of the underlying server object.  It would have
        # the benefit of putting all the logic for handling the server IP
        # address configuration in devices/server.py.
        if config.has_option('server', 'ipAddress'):
            serverIp = config.get('server', 'ipAddress')
        else:
            serverIp = '127.0.0.1'
        self.connobj = util.connection.Connection(
            'Andorcam', self.config.get('ipAddress'), self.config.get('port'),
            localIp = serverIp)
        ## List of valid image size strings.
        self.imageSizes = ['Full (2560x2160)', 'Quarter (1392x1040)',
                '540x512', '240x256', '144x128']
        self.exposureTime = None
        self.minExposureTime = None
        self.timeBetweenExposures = None
        ## Current trigger mode for cameras.
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE
        ## Queue of (image, timestamp, camera name) representing images
        # received from the camera computer(s).
        self.imageQueue = Queue.Queue()

        ## Partial image that we are in the process of reconstructing from
        # portions sent to us by the camera computer (only relevant for
        # large image sizes).
        self.partialImage = None
        ## Timestamp for partial images.
        self.partialImageTimestamp = None

        self.handler = None

        self.publishImages()


    def cleanupAfterExperiment(self):
        # Switch camera back to external exposure mode.
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE
        if self.connobj.connection is not None:
            self.connobj.connection.setTrigger(self.curTriggerMode)


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                         self.cleanupAfterExperiment)


    def getHandlers(self):
        """Returns the handler for the camera."""
        #for name, ipAddress, port in [('Zyla', '10.0.0.2', 7000)]:
        result = handlers.camera.CameraHandler(
            "%s" % self.config.get('label'), "sCMOS camera", 
            {'setEnabled': self.enableCamera, 
             'getImageSize': self.getImageSize, 
             'getTimeBetweenExposures': self.getTimeBetweenExposures, 
             'prepareForExperiment': self.prepareForExperiment,
             'getExposureTime': self.getExposureTime,
             'setExposureTime': self.setExposureTime,
             'getImageSizes': self.getImageSizes,
             'setImageSize': self.setImageSize,
             'getMinExposureTime': self.getMinExposureTime},
            handlers.camera.TRIGGER_BEFORE)
        self.handler = result
        return result


    def enableCamera(self, name, isOn):
        """Enable or disable the hardware."""
        if isOn:
            self.connobj.connect(lambda *args: self.receiveData(*args))
            # Set 540x512 image size.
            self.connobj.connection.setCrop(2)
            # Switch to external exposure mode.
            self.connobj.connection.setTrigger(self.curTriggerMode)
        else:
            self.connobj.disconnect()
        self.invalidateCaches()


    ## Clear our caches for a given camera, so that they must be reacquired.
    def invalidateCaches(self):
        self.exposureTime = None
        self.minExposureTime = None
        self.timeBetweenExposures = None
        # Reacquire values for the min exposure time now, since otherwise
        # we risk trying to get them in the preparation for an experiment,
        # at which point the camera's state has been changed; this makes
        # the experiment not work.
        self.getMinExposureTime(self.name)


    ## Receive data from a camera. 
    def receiveData(self, action, *args):
        if action == 'new image':
            # Received a new image in its entirety.
            (image, timestamp) = args
            self.imageQueue.put((image, timestamp, self.name))
        elif action == 'image component info':
            # We'll be receiving pieces of an image in multiple messages;
            # start assembling them into a complete image.
            # \todo This logic doesn't cope with multiple cameras (i.e.
            # self.partialImage should be a mapping of camera name to
            # partial images).
            (shape, timestamp) = args
            self.partialImageTimestamp = timestamp
            self.partialImage = numpy.zeros(shape, dtype = numpy.uint16)
        elif action == 'image component':
            # Received a component of the image.
            (xOffset, yOffset, image) = args
            self.partialImage[xOffset : xOffset + image.shape[0],
                    yOffset : yOffset + image.shape[1]] = image
        elif action == 'image complete':
            # Done receiving image components.
            self.imageQueue.put(
                    (self.partialImage, self.partialImageTimestamp, self.name)
            )


    ## Publish images we have received. We do this in a separate thread from
    # the thread that receives the images to avoid keeping the network link
    # to the camera computer occupied.
    @util.threads.callInNewThread
    def publishImages(self):
        while True:
            # Wait for an image to arrive.
            image, timestamp, name = self.imageQueue.get(block = True,
                    timeout = None)
            events.publish("new image %s" % name, image, timestamp)


    def getImageSize(self, name):
        """Read the image size from the camera."""
        return self.connobj.connection.getImageShape()


    def getTimeBetweenExposures(self, name, isExact = False):
        """Get the amount of time, in milliseconds, between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started."""
        if self.timeBetweenExposures is None:
            # Set the cached value.
            self.timeBetweenExposures = (
                self.connobj.connection.getReadoutTime() * 1000 + .05)
        val = self.timeBetweenExposures
        if isExact:
            val = decimal.Decimal(val)
        return val


    def setExposureTime(self, name, newTime):
        """Sets the exposure time, in milliseconds."""
        # Input may be a decimal.Decimal object, but we can only operate on
        # floats.
        newTime = float(newTime)
        # Coerce exposure time to be at least the minimum; convert from
        # millseconds to seconds.
        newTime = max(self.getMinExposureTime(name), newTime) / 1000
        if (self.exposureTime is not None and
            abs(self.exposureTime - newTime) < .0001):
            # We're already there; don't bother.
            return
        self.connobj.connection.setExposureTime(newTime)
        self.connobj.connection.setTrigger(self.curTriggerMode)
        self.exposureTime = newTime


    def getExposureTime(self, name, isExact = False):
        """Reads the camera's exposure time and returns the value, in
        milliseconds."""
        val = self.connobj.connection.getExposureTime()
        if isExact:
            return decimal.Decimal(val) * (decimal.Decimal(1000.0))
        return val * 1000.0


    def getMinExposureTime(self, name):
        """Returns the minimum exposure time, in milliseconds, that is possible
        for the camera.
        """
        # Unfortunately there's no API call for this, so we have to derive it
        # by setting an absurdly low time, reseting the trigger mode, and then
        # checking the actual exposure time.
        # Because of the extra actions, getting this value is nontrivial, so
        # we cache it.
        if self.minExposureTime is not None:
            return self.minExposureTime
        if self.connobj.connection is None:
            # Can't do anything.
            return
        curExposureTime = self.connobj.connection.getExposureTime()
        self.connobj.connection.setExposureTime(.00001)
        self.connobj.connection.setTrigger(self.curTriggerMode)
        # Convert from seconds to milliseconds
        result = self.connobj.connection.getExposureTime() * 1000
        self.connobj.connection.setExposureTime(curExposureTime)
        self.minExposureTime = result
        print "Min exposure time is",result
        return result


    def getImageSizes(self, name):
        """Returns a list of strings describing available image sizes."""
        return self.imageSizes


    ## Set the image size for the camera.
    def setImageSize(self, name, size):
        self.connobj.connection.setCrop(self.imageSizes.index(size))
        self.connobj.connection.setTrigger(self.curTriggerMode)
        # Readout time has changed.
        self.invalidateCaches()


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        exposureTime = experiment.getExposureTimeForCamera(self.handler)
        self.setExposureTime(name, exposureTime)
        self.connobj.connection.setTrigger(TRIGGER_EXTERNAL)
        self.curTriggerMode = TRIGGER_EXTERNAL


class CameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorCMOSCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
