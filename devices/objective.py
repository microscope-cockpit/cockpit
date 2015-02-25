## This dummy device presents a selection of objectives to the user. In
# practice, the only difference you might have to make to this device to use
# it would be to change the available objectives and their pixel sizes.

import device
import handlers.objective
import re
from config import config
CONFIG_NAME = 'objectives'
PIXEL_PAT =  r"(?P<pixel_size>\d*[.]?\d*)"
TRANSFORM_PAT = r"(?P<transform>\(\s*\d*\s*,\s*\d*\s*,\s*\d*\s*\))"
CONFIG_PAT = PIXEL_PAT + r"\s*(,|;)\s*" + TRANSFORM_PAT

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
        pixel_sizes = {}
        transforms = {}
        if config.has_section(CONFIG_NAME):
            objectives = config.options(CONFIG_NAME)
            for obj in objectives:
                cfg = config.get(CONFIG_NAME, obj)
                parsed = re.search(CONFIG_PAT, cfg).groupdict()
                try:
                    transform = eval(parsed['transform'])
                except:
                    transform = (0,0,0)
                pixel_sizes.update({obj: float(parsed['pixel_size'])})
                transforms.update({obj: transform})
        else:
            pixel_sizes = DUMMY_OBJECTIVE_PIXEL_SIZES
            transforms = {obj: (0,0,0) for obj in pixel_sizes.keys()}

        default = pixel_sizes.keys()[0]

        return [handlers.objective.ObjectiveHandler("objective", 
                "miscellaneous", pixel_sizes, transforms, default)]
