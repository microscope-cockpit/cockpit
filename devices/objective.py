## This dummy device presents a selection of objectives to the user. In
# practice, the only difference you might have to make to this device to use
# it would be to change the available objectives and their pixel sizes.

import device
import handlers.objective
from config import config
CONFIG_NAME = 'objectives'

## Maps objective names to the pixel sizes for those objectives. This is the 
# amount of sample viewed by the pixel, not the physical size of the 
# pixel sensor.
DUMMY_OBJECTIVE_PIXEL_SIZES = {
        "40x": .2,
        "60xWater": .1,
        "60xOil": .1,
        "100xOil": .08,
        "150xTIRF": .06,
}

CLASS_NAME = 'ObjectiveDevice'

class ObjectiveDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')
        self.deviceType = "objective"


    def getHandlers(self):
        if config.has_section(CONFIG_NAME):
            objectives = config.options(CONFIG_NAME)
            OBJECTIVE_PIXEL_SIZES = {obj: float(config.get(CONFIG_NAME, obj)) 
                                        for obj in objectives}
        else:
            OBJECTIVE_PIXEL_SIZES = DUMMY_OBJECTIVE_PIXEL_SIZES

        return [handlers.objective.ObjectiveHandler("objective", 
                "miscellaneous", OBJECTIVE_PIXEL_SIZES, "100xOil")]
