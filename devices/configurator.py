## This Device handles various miscellaneous information about the microscope.

import device
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'

class ConfiguratorDevice(device.Device):
    def getHandlers(self):
        root = os.path.expanduser('~')
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

