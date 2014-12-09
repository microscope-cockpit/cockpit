""" Cockpit device for SRS SR470 shutter controller.

Mick Phillips, 2014.

This is a really simple driver for the SR470 shutter controller.  For now, all
it does is make the SR470 respond to an external trigger, although it is
feasible that the shutter controller could be programmed to control exposure
timing.
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


    def initialize(self):
        self.connection = telnetlib.Telnet(self.ipAddress, self.port, timeout=5)
        self.connection.read_until("SR470 Telnet Session:")
        # Read out any trailing whitespace, e.g. newlines.
        self.connection.read_eager()
        self.enableTrigger()


    def enableTrigger(self):
        # Set the shutter to 'normally closed'.
        self.send("POLR 1")
        # Set the control mode to external level. The shutter will be open as
        # long as the external input is high.
        self.send("SRCE 2")


    def onPrepareForExperiment(self, experiment):
        if config.has_section('dsp'):
            ## Rely on the DSP for timing: use external level control.
            # DSP trigger line is configured elsewhere.
            self.enableTrigger()
        else:
            ## We could use the SR470 controller for exposure timing here.
            pass


    def onCleanupAfterExperiment(self):
        # Assert shutter closed (also reverts to internal triggering).
        self.send("ASRT 0")
        self.enableTrigger()


    def send(self, command):
        self.connection.write(command + '\n')
        return self.connection.read_until('\n', 0.05)
