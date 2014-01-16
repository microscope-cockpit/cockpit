
import depot
import device
import handlers.objective
import microManager

import re


CLASS_NAME = 'ObjectiveDevice'


## This controls the objective turret.
class ObjectiveDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # We need to initialize after the microManager device.
        self.priority = 1000
        ## Reference to the MMCore object.
        self.core = None


    def initialize(self):
        self.core = depot.getDevice(microManager).getCore()

        
    def getHandlers(self):
        objectiveNames = self.core.getAllowedPropertyValues('TINosePiece', 'Label')
        # Try to extract the magnification factor from the objective name.
        nameToPixelSize = {}
        for name in objectiveNames:
            match = re.search('(\d+)x', name)
            if match:
                factor = int(match.group(1))
                # This is empirically-derived from the 10x objective and
                # shouldn't be considered precise.
                nameToPixelSize[name] = 8000.0 / 512.0 / factor
            else:
                # Give up; make something up.
                nameToPixelSize[name] = 1
        curObj = self.core.getProperty('TINosePiece', 'Label')
        return [handlers.objective.ObjectiveHandler("objective", 
                "miscellaneous", nameToPixelSize, curObj,
                callbacks = {'setObjective': self.setObjective})
        ]


    ## Don't actually move the objective turret, due to fear we could
    # accidentally destroy objectives.
    def setObjective(self, name, newObjective):
        pass
