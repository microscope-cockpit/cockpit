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
        # 
        self.isActive = config.has_section(CONFIG_NAME)
        if self.isActive:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = config.get(CONFIG_NAME, 'port')
            self.controlledLightNames = set(
                config.get(CONFIG_NAME, 'lights').split(';'))
            events.subscribe('prepare for experiment', 
                            self.onPrepareForExperiment)
            events.subscribe('experiment complete', 
                            self.onCleanupAfterExperiment)
        ## Set of handlers we control.
        self.handlers = set()
        ## Our ExperimentExecutor handler.
        self.executor = None
        ## Cached exposure times we have set.
        self.nameToExposureTime = {}
        ## Cached trigger response delay
        self.curDelay = None


    def initialize(self):
        self.connection = telnetlib.Telnet(self.ipAddress, self.port, timeout=5)
        self.connection.read_until("SR470 Telnet Session:")
        # Read out any trailing whitespace, e.g. newlines.
        self.connection.read_eager()


    def onPrepareForExperiment(self, experiment):
        if config.has_section('dsp'):
            ## Rely on the DSP for timing: use external level control.
            # DSP trigger line is configured elsewhere.
            self.connection.write("SRCE 2")
        else:
            ## We could use the SR470 controller for exposure timing here.
            pass


    def onCleanupAfterExperiment(self):
        ## Assert shutter closed (also reverts to internal triggering).
        self.connection.write("ASRT 0")


    def sendCommand(self, command):
        self.connection.write(command + '\n')
        return self.connection.read_until('\n', 0.05)
