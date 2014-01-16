## This Device handles various miscellaneous information about the microscope.

import device
import experiment.experimentRegistry
import experiment.structuredIllumination
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'

class ConfiguratorDevice(device.Device):
    ## This scope can use SI experiments
    def initialize(self):
        # Insert just after Z-stack experiments.
        experiment.experimentRegistry.registerModule(experiment.structuredIllumination, 1)

        
    def getHandlers(self):
        root = 'F:' + os.path.sep
        config = {
                'slideAltitude': 7370,
                'slideTouchdownAltitude': 7900,
                'dishAltitude': 5750,
                'dataDirectory': os.path.join(root, 'MUI_DATA'),
                'logDirectory': os.path.join(root, 'MUI_LOGS'),
                'configDirectory': os.path.join(root, 'MUI_CONFIG'),
        }
        return [handlers.configuratorHandler.ConfiguratorHandler(
            'configuration', 'miscellaneous', {}, config)
        ]

