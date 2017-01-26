## This module provides a dummy camera that generates test pattern images. 

import device
import events
import handlers.camera

import decimal
import numpy
import scipy
import time
import wx
import gui

# An instance of this class is created if no real cameras are found by depot.
CLASS_NAME = 'DummyCameraDevice'
IMAGE_SIZES = ['512x512','256x512']

## An important clarification about this system: normally the assumption is that
# cameras will be driven by external trigger. Thus there's no "take image" 
# function here. Some external software is expected to notice when the camera
# has taken an image and send it to us here, at which point it is propagated
# to the rest of the cockpit. Because this is a dummy camera, we don't have
# exactly that system in place.
class DummyCameraDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Mapping of camera name to that camera's image size in pixels 
        # (as an index into IMAGE_SIZES).
        self.nameToImageSize = {}
        ## Cached copy of the exposure time, in milliseconds.
        self.curExposureTime = 100
        ## Mapping of camera name to whether or not that camera is ready 
        # to take images.
        self.nameToIsReady = {}
        ## Incrementor for generating test patterns.
        self.imageCount = 0
        ## Number of bars in the test image
        self.numBars = 16
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')
        self.deviceType = "camera"


    def performSubscriptions(self):
        events.subscribe("dummy take image", self.onDummyImage)


    ## Generate a couple of camera handlers that are hooked up to our dummy
    # functions.
    def getHandlers(self):
        result = []
        for i in range(1, 5):
            name = 'Dummy camera %d' % i
            result.append(handlers.camera.CameraHandler(
                name, "Dummy cameras", 
                {'setEnabled': self.enableCamera, 
                    'getImageSize': self.getImageSize, 
                    'getTimeBetweenExposures': self.getTimeBetweenExposures, 
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize,
                    'makeUI': self.makeUI,
                    },
                True))
            self.nameToIsReady[name] = False
            self.nameToImageSize[name] = 0 
        return result


    ## Handle a camera connecting or disconnecting.
    def enableCamera(self, name, isOn):
        # Simulate typical camera-init. delay.
        time.sleep(1)
        self.nameToIsReady[name] = isOn
        return isOn


    ## Get the size, in pixels, of the image this camera generates.
    def getImageSize(self, name):
        width, height = IMAGE_SIZES[self.nameToImageSize[name]].split('x')
        width = int(width)
        height = int(height)
        return (width, height)


    ## Get the time between exposures -- i.e. the time spent reading
    # out the sensor. Result is in milliseconds.
    def getTimeBetweenExposures(self, name, isExact = False):
        # In reality this usually depends on the current image size...
        val = 33
        if isExact:
            return decimal.Decimal(val)
        return val


    ## Change the exposure time. For this set of dummy cameras we use the same
    # exposure time for both of them.
    # \param time New exposure time, in milliseconds.
    def setExposureTime(self, name, msTime):
        self.curExposureTime = msTime


    ## Get the exposure time for this camera, in milliseconds.
    def getExposureTime(self, name, isExact = False):
        val = self.curExposureTime
        if isExact:
            return decimal.Decimal(val)
        return val


    ## Get a list of valid image sizes for the camera. In our case this does
    # not depend on the camera in question.
    def getImageSizes(self, name):
        return IMAGE_SIZES


    ## Set the image size for the camera. 
    # \param size String from IMAGE_SIZES.
    def setImageSize(self, name, size):
        self.nameToImageSize[name] = IMAGE_SIZES.index(size)


    ## Get the camera ready for an experiment. 
    def prepareForExperiment(self, name, experiment):
        pass
    

    ## Pretend that we've just received an image from the camera hardware;
    # propagate it to the rest of the cockpit.
    # \param camera For experiments, we only trigger one camera at a time. 
    def onDummyImage(self, camera = None):
        for name, isReady in self.nameToIsReady.iteritems():
            if not isReady or (camera and name != camera.name):
                # Camera is not enabled, or is the wrong camera.
                continue
            width, height = self.getImageSize(name)
            row = numpy.zeros(width)
            row[:] = [numpy.sin(i * numpy.pi / self.numBars) for i in xrange(width)]
            image = numpy.empty((width, height))
            image[:] = row
            # Rotate the test pattern.
            angle = numpy.deg2rad(self.imageCount * 10)
            cosTheta = numpy.cos(-angle)
            sinTheta = numpy.sin(-angle)
            transform = numpy.array([[cosTheta, sinTheta], [-sinTheta, cosTheta]])
            inverted = numpy.linalg.inv(transform)
            offset = -numpy.dot(inverted, (height / 2, width / 2)) + (height / 2, width / 2)
            image = scipy.ndimage.affine_transform(image, inverted, 
                    offset = offset, order = 1)
            image -= image.min()
            image *= (2 ** 16 / image.max())
            image = image.astype(numpy.uint16)
            events.publish('new image %s' % name, image, time.time())
            self.imageCount += 1


    def makeUI(self, parent):
        devPanel = wx.Panel(parent)
        devSizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(
                parent=devPanel, label='from device')
        devSizer.Add(label)

        devButton = gui.toggleButton.ToggleButton(
                label="A button",
                parent=devPanel)
        devSizer.Add(devButton)

        devPanel.SetSizerAndFit(devSizer)
        return devPanel