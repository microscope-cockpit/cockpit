## This Device specifies a "drawer" of optics and filters that determines
# what cameras see what lights.
# Configure it in the config file with type, camera names, and drawer
# configurations, each with one dye and one wavelength per camera.
#
#       [name]
#       type: Drawer
#       cameras: cam1, cam2
#       default: GFP: 525, Cy5: 695
#       TRITC: FITC: 518, TRITC: 600
#

from . import device
from handlers.drawer import DrawerHandler, DrawerSettings
import re

class Drawer(device.Device):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)

    def parseConfig(self, config=None):
        if config is not None:
            self.config = config
        else:
            config = self.config
        cameras = re.split('[;, ]\s*', config['cameras'])
        settings = []
        for key, item in config.items():
            if key in ['type', 'cameras']:
                continue
            filters = re.split('[,;]\s*', item)
            if filters:
                if len(filters) != len(cameras):
                    raise Exception('Drawer: mismatch between number of cameras and filters.')
                dyes, wls = zip(*[re.split('[:]\s*', f) for f in filters])
                settings.append(DrawerSettings(key, cameras, dyes, wls))
        return settings


    def getHandlers(self):
        # Just return an empty handler for now. It will be configured
        # after the cameras have been initialized.
        settings = self.parseConfig()
        self.handler = DrawerHandler("drawer", "miscellaneous",
                                        settings, 0, None)
        return [self.handler]