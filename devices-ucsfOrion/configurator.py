## This Device handles various miscellaneous information about the microscope.

import device
import experiment.experimentRegistry
import experiment.optoScriptExample
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'

class ConfiguratorDevice(device.Device):
    ## This scope can use opto experiments.
    def initialize(self):
        experiment.experimentRegistry.registerModule(experiment.optoScriptExample)

        
    def getHandlers(self):
        root = 'C:\\'
        config = {
                'slideAltitude': 7370,
                'slideTouchdownAltitude': 7900,
                'dishAltitude': 5750,
                'dataDirectory': os.path.join(root, 'AA_MUI_DATA'),
                'logDirectory': os.path.join(root, 'AA_MUI_LOGS'),
                'configDirectory': os.path.join(root, 'AA_MUI_CONFIG'),
        }
        return [handlers.configuratorHandler.ConfiguratorHandler(
            'configuration', 'miscellaneous', {}, config)
        ]

