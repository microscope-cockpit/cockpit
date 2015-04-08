import device
import handlers.objective

## Maps objective names to the pixel sizes for those objectives.
OBJECTIVE_PIXEL_SIZES = {
        "60xWaterEM": .08009,
        "60xWaterCMOS": .08667, 
}

CLASS_NAME = 'ObjectiveDevice'

class ObjectiveDevice(device.Device):
    def getHandlers(self):
        return [handlers.objective.ObjectiveHandler(
                "objective", 
                "miscellaneous",
                OBJECTIVE_PIXEL_SIZES,
                { obj: (0, 0, 0) for obj in OBJECTIVE_PIXEL_SIZES.keys() },
                { obj: (0, 0, 0) for obj in OBJECTIVE_PIXEL_SIZES.keys() },
                "60xWaterCMOS")]
