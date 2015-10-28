## This Device specifies a "drawer" of optics and filters that determines
# what cameras see what lights.

import device
import handlers.drawer
from config import CAMERAS

CLASS_NAME = 'DrawerDevice'

class DrawerDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)


    def getHandlers(self):
        # Just return an empty handler for now. It will be configured
        # after the cameras have been initialized.
        self.handler = handlers.drawer.DrawerHandler("drawer", "miscellaneous",
                                                       None, 0, None)
        return [self.handler]


