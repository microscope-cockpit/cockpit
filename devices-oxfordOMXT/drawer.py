## This Device specifies a "drawer" of optics and filters that determines
# what cameras see what lights.

import device
import handlers.drawer

## Maps dye names to colors to use for those dyes.
DYE_TO_COLOR = {
        'Cy5': (0, 255, 255),
        'DAPI': (184, 0, 184),
        'DIC': (128, 128, 128),
        'FITC': (80,255,150),
        'GFP': (0, 255, 0),
        'mCherry': (255, 0, 0),
        'RFP': (255, 0, 0),
        'Rhod': (255,80,20),
        'YFP': (255, 255, 0),
}

CLASS_NAME = 'DummyDrawerDevice'

class DummyDrawerDevice(device.Device):
    def getHandlers(self):
        # Note that these names have to be the same as the names used for the
        # CameraHandler instances created by other devices.
        cameraNames = ('West','East')
        drawerNames = ('Dummy drawer 1', 'Dummy drawer 2')
        dyes = [('GFP','mCherry'), ('Cy5','FITC')]
        wavelengths = [(525,620), (695,525)]
        settings = []
        for i, name in enumerate(drawerNames):
            colors = [DYE_TO_COLOR[d] for d in dyes[i]]
            settings.append(handlers.drawer.DrawerSettings(
                name, cameraNames, dyes[i], colors, wavelengths[i])
            )
        return [handlers.drawer.DrawerHandler("drawer", "miscellaneous",
                settings, 0)]

