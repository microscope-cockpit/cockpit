## This dummy device presents a selection of objectives to the user. In
# practice, the only difference you might have to make to this device to use
# it would be to change the available objectives and their pixel sizes.

import device
import handlers.objective

## Maps objective names to the pixel sizes for those objectives. This is the 
# amount of sample viewed by the pixel, not the physical size of the 
# pixel sensor.
OBJECTIVE_PIXEL_SIZES = {
        "40x": .198,
        "60xWater": .132,
        "60xOil": .132,
        "100xOil": .0792,
        "150xTIRF": .0528,
}

CLASS_NAME = 'ObjectiveDevice'

class ObjectiveDevice(device.Device):
    def getHandlers(self):
        return [handlers.objective.ObjectiveHandler("objective", 
                "miscellaneous", OBJECTIVE_PIXEL_SIZES, "100xOil")]
