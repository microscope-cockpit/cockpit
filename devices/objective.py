## This dummy device presents a selection of objectives to the user. In
# practice, the only difference you might have to make to this device to use
# it would be to change the available objectives and their pixel sizes.

import device
import handlers.objective
import re
PIXEL_PAT =  r"(?P<pixel_size>\d*[.]?\d*)"
LENSID_PAT = r"(?P<lensID>\d*)"
TRANSFORM_PAT = r"(?P<transform>\(\s*\d*\s*,\s*\d*\s*,\s*\d*\s*\))"
OFFSET_PAT = r"(?P<offset>\(\s*[-]?\d*\s*,\s*[-]?\d*\s*,\s*[-]?\d*\s*\))?"
COLOUR_PAT = r"(?P<colour>\(\s*[-]?\d*\s*,\s*[-]?\d*\s*,\s*[-]?\d*\s*\))?"

CONFIG_PAT = PIXEL_PAT + r"(\s*(,|;)\s*)?" + LENSID_PAT + r"(\s*(,|;)\s*)?" + TRANSFORM_PAT + r"(\s*(,|;)\s*)?" + OFFSET_PAT+ r"(\s*(,|;)\s*)?" + COLOUR_PAT

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
    def __init__(self, name='objectives', config={}):
        device.Device.__init__(self, name, config)
        # Set priority to Inf to indicate that this is a dummy device.

    def getHandlers(self):
        pixel_sizes = {}
        transforms = {}
        offsets = {}
        lensIDs = {}
        colours = {}
        if not self.config:
            # No objectives section in config
            pixel_sizes = DUMMY_OBJECTIVE_PIXEL_SIZES
            transforms = {obj: (0,0,0) for obj in pixel_sizes.keys()}
            offsets = {obj: (0,0,0) for obj in pixel_sizes.keys()}
            lensIDs = {obj: 0 for obj in pixel_sizes.keys()}
            colours = {obj: (1,1,1) for obj in pixel_sizes.keys()}
        else:
            for obj, cfg in self.config.items():
                parsed = re.search(CONFIG_PAT, cfg)
                if not parsed:
                    # Could not parse config entry.
                    raise Exception('Bad config: objectives.')
                    # No transform tuple
                else:    
                    pstr = parsed.groupdict()['pixel_size']
                    lstr = parsed.groupdict()['lensID']
                    tstr = parsed.groupdict()['transform']
                    ostr =  parsed.groupdict()['offset']
                    cstr =  parsed.groupdict()['colour']
                    pixel_size = float(pstr)
                    lensID = int(lstr) if lstr else 0
                    transform = eval(tstr) if tstr else (0,0,0)
                    offset = eval(ostr) if ostr else (0,0,0)
                    colour = eval(cstr) if cstr else (1,0,0)
                pixel_sizes.update({obj: pixel_size})
                lensIDs.update({obj: lensID})
                transforms.update({obj: transform})
                offsets.update({obj: offset})
                colours.update({obj: colour})

        default = pixel_sizes.keys()[0]

        return [handlers.objective.ObjectiveHandler("objective",
                                                    "miscellaneous",
                                                    pixel_sizes,
                                                    transforms,
                                                    offsets,
                                                    colours,
                                                    lensIDs,
                                                    default)]
