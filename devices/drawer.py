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
        handler = handlers.drawer.DrawerHandler("drawer", "miscellaneous",
                None, 0, None)
        for camera, config in CAMERAS.iteritems():
            filters = map(lambda d, w: {'dye': d, 'wavelength': w},
                         config['dyes'],
                         config['wavelengths'])
            handler.addCamera(camera, filters)
        
        # Add the dummy cameras, too.
        cameraNames = ('Dummy camera 1', 'Dummy camera 2', 'Dummy camera 3', 'Dummy camera 4')
        drawerNames = ('Dummy drawer 1', 'Dummy drawer 2')
        dyes = [('GFP', 'Cy5', 'mCherry', 'DAPI'), 
                ('Cy5', 'FITC', 'Rhod', 'DAPI')]
        wavelengths = [(525, 670, 585, 447), (695, 518, 590, 450)]
        for i, camera in enumerate(cameraNames):
            filters = map(lambda d, w: {'dye': d, 'wavelength': w}, 
                [dye[i] for dye in dyes],
                [wavelength[i] for wavelength in wavelengths])
            handler.addCamera(camera, filters)

        return [handler]
