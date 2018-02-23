## This module provides a dummy camera that generates test pattern images. 

from . import device


## CameraDevice subclasses Device with some additions appropriate
# to any camera.
class CameraDevice(device.Device):
    from collections import namedtuple
    from numpy import rot90, flipud, fliplr


    # Tuple of booleans: what transforms do we need to apply to recieved data?
    # A derived class should set the state of each according to the camera
    # position and orientation.
    Transform = namedtuple('Transform', 'rot90, flip_h, flip_v')


    def __init__(self, name, camConfig):
        super(CameraDevice, self).__init__(name, camConfig)
        # Set transform according to config, or default to null transform.
        transform = camConfig.get('transform', '')
        if not transform:
            self.transform = self.Transform(None, None, None)
        else:
            self.transform = self.Transform(*camConfig.get('transform'))


    def orient(self, image):
        """Apply transforms to an image to put it in the correction orientation.

        Some cameras may do this on the hardware or remote server. Those that
        don't should call this method on the received data before publishing
        a 'new image' event.
        """
        transform = self.transform
        if transform.rot90:
            numpy.rot90(image, transform.rot90)
        if transform.flip_h:
            numpy.fliplr(image)
        if transform.flip_v:
            numpy.flipud(image)
