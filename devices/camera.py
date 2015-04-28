## This module provides a dummy camera that generates test pattern images. 

import device
from config import CAMERAS
import wx

## CameraDevice subclasses Device with some additions appropriate
# to any camera.
class CameraDevice(device.Device):
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



class CameraManager(device.Device):
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


    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        outerSizer = wx.BoxSizer(wx.VERTICAL)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        for cam in self.cameras:
            if hasattr(cam, 'makeUI'):
                rowSizer.Add(cam.makeUI(self.panel))
                rowSizer.AddSpacer(12)
        outerSizer.Add(rowSizer)
        self.panel.SetSizerAndFit(outerSizer)
        return self.panel


    def performSubscriptions(self):
        for camera in self.cameras:
            camera.performSubscriptions()
