## This Device handles various miscellaneous information about the microscope.

import device
import experiment.experimentRegistry
import experiment.structuredIllumination
import experiment.zStackMulti
import handlers.configuratorHandler

import os

CLASS_NAME = 'ConfiguratorDevice'
CONFIG_NAME = 'base'

from config import config


class ConfiguratorDevice(device.Device):
    ## This scope can use SI experiments
    def initialize(self):
        # Insert just after Z-stack experiments.
        experiment.experimentRegistry.registerModule(experiment.structuredIllumination, 1)
        experiment.experimentRegistry.registerModule(experiment.zStackMulti)

        
    def getHandlers(self):
        root = config.get(CONFIG_NAME, 'root', 'C:' + os.path.sep)
        prefix = config.get(CONFIG_NAME, 'dirname_prefix', 'AA_MUI_')

        # Default values.
        configdict = {
                'slideAltitude': 7370,
                'slideTouchdownAltitude': 7900,
                'dishAltitude': 5750,
                'dataDirectory': os.path.join(root, prefix + 'DATA'),
                'logDirectory': os.path.join(root, prefix + 'LOGS'),
                'configDirectory': os.path.join(root, prefix + 'CONFIG'),
                'maxFilesizeMegabytes': 1000,
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

