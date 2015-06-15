import decimal
import wx

import depot
import deviceHandler
import events


## Available trigger modes for triggering the camera.
# Trigger at the end of an exposure; trigger before the exposure;
# trigger for the duration of the exposure.
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION) = range(3)



## This handler is for cameras, of course. Cameras provide images to the 
# microscope, and are assumed to be usable during experiments. 
class CameraHandler(deviceHandler.DeviceHandler):
    ## Create the Handler. 
    # callbacks should fill in the following functions:
    # - setEnabled(name, shouldEnable): Turn the camera "on" or "off".
    # - getImageSize(name): Return a (width, height) tuple describing the size
    #   in pixels of the image the camera takes.
    # - getTimeBetweenExposures(name, isExact): Return the minimum time between
    #   exposures for this camera, in milliseconds. If isExact is set, returns
    #   a decimal.Decimal instance.
    # - setExposureTime(name, time): Change the camera's exposure time to
    #   the specified value, in milliseconds.
    # - getExposureTime(name, isExact): Returns the time in milliseconds that
    #   the camera is set to expose for when triggered. If isExact is set,
    #   returns a decimal.Decimal instance.
    # - getImageSizes(name): Return a list of strings describing the available
    #   image sizes for this camera.
    # - setImageSize(name, size): Set the image size for this camera to one
    #   of the values returned by getImageSizes().
    # - prepareForExperiment(name, experiment): Get the camera ready for an
    #   experiment.
    # - Optional: getMinExposureTime(name): returns the minimum exposure time
    #   the camera is capable of performing, in milliseconds. If not available,
    #   0ms is used.
    # \param exposureMode One of TRIGGER_AFTER, TRIGGER_BEFORE, or
    #   TRIGGER_DURATION. The first two are for external-trigger cameras, which
    #   may be frame-transfer (trigger at end of exposure, and expose
    #   continuously) or not (trigger at beginning of exposure and expose for
    #   a pre-configured duration). The last is for external-exposure cameras,
    #   which expose for as long as you tell them to, based on the TTL line.
    # \param minExposureTime Minimum exposure duration, in milliseconds.
    #   Typically only applicable if doExperimentsExposeContinuously is True.
    
    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    def __init__(self, name, groupName, callbacks,
            exposureMode):
        # Note we assume that cameras are eligible for experiments.
        deviceHandler.DeviceHandler.__init__(self, name, groupName, True, 
                callbacks, depot.CAMERA)
        ## Color to use when camera is displayed. Depends on current drawer.
        self.color = None
        ## Descriptive name for camera. Depends on current drawer.
        self.descriptiveName = None
        ## Wavelength of light we receive. Depends on current drawer.
        self.wavelength = None
        ## True if the camera is currently receiving images.
        self.isEnabled = False
        events.subscribe('drawer change', self.onDrawerChange)
        self.exposureMode = exposureMode


    ## Update some of our properties based on the new drawer.
    # \param newSettings A devices.handlers.drawer.DrawerSettings instance.
    def onDrawerChange(self, drawerHandler):
        self.color = drawerHandler.getColorForCamera(self.name)
        dyeName = drawerHandler.getDyeForCamera(self.name)
        if dyeName:
            self.descriptiveName = dyeName + " (%s)" % self.name
        else:
            self.descriptiveName = self.name
        self.wavelength = drawerHandler.getWavelengthForCamera(self.name)


    ## Invoke our callback, and let everyone know that a new camera is online.
    @reset_cache
    def setEnabled(self, shouldEnable = True):
        self.callbacks['setEnabled'](self.name, shouldEnable)
        self.isEnabled = shouldEnable
        # Subscribe / unsubscribe to the prepare-for-experiment event.
        func = [events.unsubscribe, events.subscribe][shouldEnable]
        func('prepare for experiment', self.prepareForExperiment)


    ## Return self.isEnabled.
    def getIsEnabled(self):
        return self.isEnabled


    ## Return the size, in pixels, of images we generated.
    def getImageSize(self):
        return self.callbacks['getImageSize'](self.name)


    ## Return the amount of time, in milliseconds, that must pass after
    # ending one exposure before another can be started.
    # If isExact is specified, then we return a decimal.Decimal value instead
    # of a raw floating point value.
    @cached
    def getTimeBetweenExposures(self, isExact = False):
        return self.callbacks['getTimeBetweenExposures'](self.name, isExact)


    ## Return the minimum allowed exposure time, in milliseconds.
    @cached
    def getMinExposureTime(self, isExact = False):
        val = 0
        if 'getMinExposureTime' in self.callbacks:
            val = self.callbacks['getMinExposureTime'](self.name)
        if isExact:
            return decimal.Decimal(val)
        return val


    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, time):
        return self.callbacks['setExposureTime'](self.name, time)


    ## Return the camera's currently-set exposure time, in milliseconds.
    # If isExact is specified, then we return a decimal.Decimal value instead
    # of a raw floating point value.
    @cached
    def getExposureTime(self, isExact = False):
        return self.callbacks['getExposureTime'](self.name, isExact)


    ## Get a list of strings describing the available image sizes (in pixels).
    def getImageSizes(self):
        return self.callbacks['getImageSizes'](self.name)


    ## Set the image size to one of the options returned by getImageSizes.
    @reset_cache
    def setImageSize(self, size):
        return self.callbacks['setImageSize'](self.name, size)


    ## Do any necessary preparation for the camera to participate in an 
    # experiment.
    @reset_cache
    def prepareForExperiment(self, experiment):
        return self.callbacks['prepareForExperiment'](self.name, experiment)


    ## Simple getter.
    def getExposureMode(self):
        return self.exposureMode

 
