import camera
# import depot
import events
import handlers.camera
import util.connection
import util.threads

import decimal
import numpy
import Queue
# import threading
# import time

from config import config, CAMERAS

CLASS_NAME = 'CameraManager'
SUPPORTED_CAMERAS = ['neo', 'zyla']

## Valid trigger modes for the cameras.
(TRIGGER_INTERNAL, TRIGGER_SOFTWARE, TRIGGER_EXTERNAL, TRIGGER_EXTERNAL_START, TRIGGER_EXTERNAL_EXPOSURE) = (1, 4, 6, 2, 3) # TODO: move this to a config file

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
            serverIp = '10.6.19.11'
        self.connobj = util.connection.Connection(
            'Andorcam', self.config.get('ipAddress'), self.config.get('port'),
            localIp = serverIp)
        ## List of valid image size strings.
        self.imageSizes = ['Full (2048x2048)', 'Quarter (1024x1024)',
                '512x512', '256x256', '128x128']
        self.exposureTime = None
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
        '''
        Switch camera back to external exposure mode.
        '''
        if self.connobj.connection is not None:
            self.connobj.connection.setTrigger(self.curTriggerMode)
        self.curTriggerMode = self.connobj.connection.getTrigger()

    def performSubscriptions(self):
        '''
        Perform subscriptions for this camera.
        '''
        events.subscribe('cleanup after experiment',
                         self.cleanupAfterExperiment)

    def getHandlers(self):
        '''
        Returns the handler for the camera.
        '''
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
            handlers.camera.TRIGGER_DURATION_PSEUDOGLOBAL)
        self.handler = result
        return result

    def enableCamera(self, name, isOn):
        '''
        Enable or disable the hardware.
        '''
        if isOn:
            self.connobj.connect(lambda *args: self.receiveData(*args))
            # Set 512x512 image size.
            self.connobj.connection.setCrop(2)
            # Switch to external exposure mode.
            self.connobj.connection.setTrigger(self.curTriggerMode)
        else:
            self.connobj.disconnect()
        self.invalidateCaches()

    def invalidateCaches(self):
        '''
        Clear our caches for a given camera, so that they must be reacquired.
        '''
        self.exposureTime = None
        self.timeBetweenExposures = None
        # Reacquire values for the min exposure time now, since otherwise
        # we risk trying to get them in the preparation for an experiment,
        # at which point the camera's state has been changed; this makes
        # the experiment not work.
        self.getMinExposureTime(self.name)

    def receiveData(self, action, *args):
        '''
        Receive data from a camera.
        '''
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
            self.imageQueue.put((self.partialImage, self.partialImageTimestamp, self.name))

    @util.threads.callInNewThread
    def publishImages(self):
        '''
        Publish images we have received. We do this in a separate thread from
        the thread that receives the images to avoid keeping the network link
        to the camera computer occupied.
        '''
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
                self.connobj.connection.getReadoutTime() * 1000 + .005)

                # add 20 Sensor Speed Clock Cycles = .0002 at 100MHz so we stay in the save side
        val = self.timeBetweenExposures
        if isExact:
            val = decimal.Decimal(val)
        return val

    def setExposureTime(self, name, newTime):
        '''
        Sets the exposure time, in milliseconds.
        '''
        # Input may be a decimal.Decimal object, but we can only operate on floats.
        newTime = float(newTime)
        # Coerce exposure time to be at least the minimum; convert from
        # millseconds to seconds.
        newTime = max(self.getMinExposureTime(name), newTime) / 1000
        if (self.exposureTime is not None and
            abs(self.exposureTime - newTime) < .0001):
            # We're already there; don't bother.
            return
        self.connobj.connection.setExposureTime(newTime)
        self.connobj.connection.setTrigger(TRIGGER_EXTERNAL_EXPOSURE)
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE
        self.exposureTime = newTime

    def getExposureTime(self, name, isExact = False):
        '''
        Reads the camera's exposure time and returns the value, in milliseconds.
        '''
        val = self.connobj.connection.getExposureTime()
        if isExact:
            return decimal.Decimal(val) * (decimal.Decimal(1000.0))
        return val * 1000.0

    def getMinExposureTime(self, name):
        '''
        Returns the minimum exposure time, in milliseconds, that is possible
        for the camera.
        '''
        if self.connobj.connection is None:
            # Can't do anything.
            return
        # Convert from seconds to milliseconds
        return self.connobj.connection.getMinExposureTime() * 1000

    def getImageSizes(self, name):
        '''
        Returns a list of strings describing available image sizes.
        '''
        return self.imageSizes

    def setImageSize(self, name, size):
        '''
        Set the image size for the camera.
        '''
        self.connobj.connection.setCrop(self.imageSizes.index(size))
        self.connobj.connection.setTrigger(self.curTriggerMode)
        # Readout time has changed.
        self.invalidateCaches()

    def prepareForExperiment(self, name, experiment):
        '''
        Make the hardware ready for an experiment.
        '''
        print('Preparing for experiment')
        exposureTime = experiment.getExposureTimeForCamera(self.handler)
        self.setExposureTime(name, exposureTime)
        self.connobj.connection.setTrigger(TRIGGER_EXTERNAL_EXPOSURE)
        self.curTriggerMode = TRIGGER_EXTERNAL_EXPOSURE

    def takeBurst(self, name, frameCount):
        self.connobj.connection.setFrameCount(frameCount)
        print('FrameCount is: ' + str(self.connobj.connection.getFrameCount()))
        print('Trigger Mode is: ' + str(self.connobj.connection.getTrigger()))
        self.connobj.connection.startAcquisition()

class CameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorCMOSCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS
