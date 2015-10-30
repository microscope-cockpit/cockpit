## This Device specifies a "drawer" of optics and filters that determines
# what cameras see what lights.

import depot
import device
import handlers.drawer
from config import config, CAMERAS

CLASS_NAME = 'DrawerDevice'
CONFIG_NAME = 'drawer'

DUMMY_DYES = [('GFP', 'TRITC', 'mCherry', 'DAPI'), ('Cy5', 'FITC', 'Rhod', 'DAPI')]
DUMMY_WAVELENGTHS = [(525, 600, 585, 447), (695, 518, 590, 450)]


class DrawerDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)


    def getHandlers(self):
        # Just return an empty handler for now. It will be configured
        # after the cameras have been initialized.
        self.handler = handlers.drawer.DrawerHandler("drawer", "miscellaneous",
                                                       None, 0, None)
        return [self.handler]


    def finalizeInitialization(self):
        handler = self.handler
        # Iterate over all cameras.
        for camera in depot.getHandlersOfType(depot.CAMERA):
            # Determine what type of filters this camera has.
            if config.has_option(CONFIG_NAME, camera.name):
                method = config.get(CONFIG_NAME, camera.name)
            else:
                method = 'static'

            # Define the filters according to the method.
            if method == 'static':
                # A drawer of static filters
                if camera.name in CAMERAS.keys():
                    # Fetch filters from camera definition.
                    filters = map(lambda d, w: {'dye': d, 'wavelength': w},
                                 CAMERAS[camera.name]['dyes'],
                                 CAMERAS[camera.name]['wavelengths'])
                elif camera.name.startswith('Dummy camera '):
                    # This is a dummy camera.
                    i = int(camera.name.split()[-1]) - 1
                    filters = map(lambda d, w: {'dye': d[i], 'wavelength': w[i]}, 
                                    DUMMY_DYES,
                                    DUMMY_WAVELENGTHS)
                else:
                    # No filter defined.
                    filters = [{'dye': None, 'wavelength': None}]
            elif method == 'wheel':
                # A filter wheel will update the drawer.
                filters = [{'dye': None, 'wavelength': None}]

            handler.addCamera(camera.name, filters)
