
## This serves as the base class for any Device subclass. Devices are as close
# as MUI gets to speaking directly to hardware. Device implementation is 
# largely left up to the client; this class simply provides a framework of 
# stub functions that must be implemented. 
class Device(object):
    def __init__(self):
        ## Set to False to disable this device. Disabled devices will not be 
        # initialized on startup. 
        self.isActive = True
        ## Priority for initializing this device. Devices with lower priorities
        # are initialized first. This is useful if you have Devices that 
        # rely on other Devices. 
        self.priority = 100


    ## Perform any necessary initialization (e.g. connecting to hardware).
    def initialize(self):
        pass


    ## Generate a list of DeviceHandlers representing the various capabilities
    # we are responsible for. Each DeviceHandler represents an abstract bit
    # of hardware -- for example, a generic camera, or a stage mover along
    # a single axis, or a light source. Take a look at the 
    # "handlers/deviceHandler.py" file for more information.
    def getHandlers(self):
        return []


    ## Construct any special UI the Device needs. Most Devices will not need
    # to do anything here, but if you have settings that the user needs to be
    # able to manipulate and that the normal UI will not handle, then this 
    # is where you create your specific UI. 
    # \return a WX Sizer or Panel that will be inserted into the main controls
    #         window, or None if nothing is to be inserted. 
    def makeUI(self, parent):
        return None


    ## Subscribe to any events we care about.
    def performSubscriptions(self):
        pass


    ## Publish any needed information. This is called after all UI widgets
    # have been generated, so they are able to respond to these publications.
    def makeInitialPublications(self):
        pass


    ## Do any final actions needed, now that all of the devices are set up
    # and all initial publications and subscriptions have been made.
    def finalizeInitialization(self):
        pass


    ## Simple getter
    def getIsActive(self):
        return self.isActive


    ## Debugging function: shutdown the device preparatory to reloading 
    # the module it is contained in.
    def shutdown(self):
        raise RuntimeError("Device %s didn't implement its shutdown function" % str(self))


    ## Debugging function: re-initialize the device with the specified list
    # of handlers.
    def initWithHandlers(self, handlers):
        raise RuntimeError("Device %s didn't implement its initWithHandlers function" % str(self))


## CameraDevice subclasses Device with some additions appropriate
# to any camera.
class CameraDevice(Device):
    from collections import namedtuple
    from numpy import rot90, flipud, fliplr


    # Tuple of booleans: what transforms do we need to apply to recieved data?
    # A derived class should set the state of each according to the camera
    # position and orientation.
    Transform = namedtuple('Transform', 'rot90, flip_h, flip_v')


    def __init__(self, camConfig):
        super(CameraDevice, self).__init__()
        self.name = camConfig.get('label')
        # Set transform according to config, or default to null transform.
        transform = camConfig.get('transform', '')
        if not transform:
            self.transform = self.Transform(None, None, None)
        else:
            self.transform = self.Transform(*camConfig.get('transform'))


    def orient(self, image):
        """Apply transforms to an image to put it in the correction orientation."""
        transform = self.transform
        if transform.rot90:
            numpy.rot90(image, transform.rot90)
        if transform.flip_h:
            numpy.fliplr(image)
        if transform.flip_v:
            numpy.flipud(image)


from config import CAMERAS
class CameraManager(Device):
    """A class to manage camera devices in cockpit."""
    def __init__(self):
        super(CameraManager, self).__init__()
        self.priority = 100
        self.cameras = []

        for name, camConfig in CAMERAS.iteritems():
            camType = camConfig.get('model', '')
            if camType and camType in self._SUPPORTED_CAMERAS:
                self.cameras.append(self._CAMERA_CLASS(camConfig))
        self.isActive = len(self.cameras) > 0


    def getHandlers(self):
        """Aggregate and return handlers from managed cameras."""
        result = []
        for camera in self.cameras:
            result.append(camera.getHandlers())
        return result
