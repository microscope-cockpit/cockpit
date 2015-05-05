## This Device handles various miscellaneous information about the microscope.

import device
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'
CONFIG_NAME = 'base'

from config import config


class ConfiguratorDevice(device.Device):
    def getHandlers(self):
        root = config.get(CONFIG_NAME, 'root', 'C:' + os.path.sep)
 
        # Default values.
        configdict = {
                'slideAltitude': 4070,
                'slideTouchdownAltitude': 2000,
                'dishAltitude': 2670,
                'dataDirectory': os.path.join(root, 'AA_MUI_DATA'),
                'logDirectory': os.path.join(root, 'AA_MUI_LOGS'),
                'configDirectory': os.path.join(root, 'AA_MUI_CONFIG'),
        }


        # Update the configdict with values from config module.
        if config.has_section(CONFIG_NAME):
            for opt in config.options(CONFIG_NAME):
                if opt in configdict:
                    # Already exists. Make sure we keep the same type.
                    dtype = type(config.get(opt))
                    configdict.update({opt: type(config.get(CONFIG_NAME, opt))})
                else:
                    configdict.update({opt: config.get(CONFIG_NAME, opt)})


        return [handlers.configuratorHandler.ConfiguratorHandler(
            'configuration', 'miscellaneous', {}, configdict)
        ]

