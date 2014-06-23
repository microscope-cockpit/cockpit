""" Cockpit device for SRS SR470 shutter controller.

Mick Phillips, 2014.
Largely derived from Chris' delayGen device.
"""

import depot
import device
import events
import handlers.executor
import handlers.lightSource
import util.logger
import decimal
import re
import telnetlib
from config import config

CLASS_NAME = 'StanfordShutterDevice'
CONFIG_NAME = 'sr470'

class StanfordShutterDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
        self.port = config.get(CONFIG_NAME, 'port')
        self.controlledLightNames = set(
            config.get(CONFIG_NAME, 'lights').split(';'))
        if self.isActive:
            events.subscribe('prepare for experiment', 
                            self.prepareForExperiment)
            events.subscribe('experiment complete', 
                            self.cleanupAfterExperiment)
        
