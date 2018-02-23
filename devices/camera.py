## This module provides a dummy camera that generates test pattern images. 

from . import device


def Transform(tstr=None):
    if tstr:
        return tuple([int(t) for t in tstr.strip('()').split(',')])
    else:
        return (0, 0, 0)

## CameraDevice subclasses Device with some additions appropriate
# to any camera.
class CameraDevice(device.Device):
    def __init__(self, name, config):
        super(CameraDevice, self).__init__(name, config)
        self.settings = {}
        self.settings['baseTransform'] = Transform(config.get('transform', None))
        self.settings['pathTransfom'] = (0, 0, 0)

