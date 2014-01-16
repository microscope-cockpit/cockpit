import device
import handlers.objective

## Maps objective names to the pixel sizes for those objectives.
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
