## This Device handles various miscellaneous information about the microscope.

import devices.device as device
import handlers.configuratorHandler

import os

class Configurator(device.Device):
    def getHandlers(self):
        root = self.config.get('root', 'C:' + os.path.sep)
 
        # Default values.
        configdict = {
                'slidealtitude': 7370,
                'slideTouchdownAltitude': 7900,
                'dishaltitude': 5750,
                'dataDirectory': os.path.join(root, 'AA_MUI_DATA'),
                'logDirectory': os.path.join(root, 'AA_MUI_LOGS'),
                'configDirectory': os.path.join(root, 'AA_MUI_CONFIG'),
        }

        # Update the configdict with values from config module.
        for opt in self.config:
            if opt in configdict:
                # Already exists. Make sure we keep the same type.
                dtype = type(configdict[opt])
                configdict.update({opt: dtype(self.config.get(opt))})
            else:
                configdict.update({opt: self.config.get(opt)})


        return [handlers.configuratorHandler.ConfiguratorHandler(
            'configuration', 'miscellaneous', {}, configdict)
        ]

