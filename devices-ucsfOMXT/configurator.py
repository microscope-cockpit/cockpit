## This Device handles various miscellaneous information about the microscope.

import device
import experiment.experimentRegistry
import experiment.structuredIllumination
import experiment.zStackMulti
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'

class ConfiguratorDevice(device.Device):
    ## This scope can use SI experiments
    def initialize(self):
        # Insert just after Z-stack experiments.
        experiment.experimentRegistry.registerModule(experiment.structuredIllumination, 1)
        experiment.experimentRegistry.registerModule(experiment.zStackMulti)

        
    def getHandlers(self):
        root = 'E:' + os.path.sep
        config = {
                'slideAltitude': 7370,
                'slideTouchdownAltitude': 7900,
                'dishAltitude': 5750,
                'dataDirectory': os.path.join(root, 'MUI_DATA'),
                'logDirectory': os.path.join(root, 'MUI_LOGS'),
                'configDirectory': os.path.join(root, 'MUI_CONFIG'),
                'maxFilesizeMegabytes': 1000,
        }
        return [handlers.configuratorHandler.ConfiguratorHandler(
            'configuration', 'miscellaneous', {}, config)
        ]

