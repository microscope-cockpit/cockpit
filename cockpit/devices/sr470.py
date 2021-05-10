#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

from cockpit.devices import shutter
import telnetlib


class StanfordShutter(shutter.ShutterDevice):
    """Cockpit device for SRS SR470 shutter controller.

    This is a really simple driver for the SR470 shutter controller.
    For now, all it does is make the SR470 respond to an external
    trigger, although it is feasible that the shutter controller could
    be programmed to control exposure timing.

    Sample config entry:

    .. code:: ini

        [561nm shutter]
        type: cockpit.devices.sr470.StanfordShutter
        ipAddress: 192.168.0.10
        port: 5024
        lights: 561nm
        triggerSource: NAME_OF_EXECUTOR_DEVICE
        triggerLine: 3

    """
    def __init__(self, name, config={}):
        super().__init__(name, config)
        # Telnet connection to device
        self.connection = None


    def initialize(self):
        """ Open telnet connection and enable response to triggers. """
        self.connection = telnetlib.Telnet(self.ipAddress, self.port, timeout=5)
        self.connection.read_until(('SR470 Telnet Session:').encode())
        # Read out any trailing whitespace, e.g. newlines.
        print(self.connection.read_eager())
        self.enableTrigger()


    def enableTrigger(self, enab=True):
        # The SR470 has a 'normal' shutter state: open or closed. With external
        # level triggering, the shutter is in the 'normal' state when the 
        # external input is high. If we set the shutter to 'normally closed', a
        # low logic level from the DSP will open it, but the DSP expects to send
        # a logic high to trigger or enable a light.
        # The simplest solution is to set the shutter to 'normally open' here.
        # When we exit, we will assert that the shutter be closed for safety.
        self.send("POLR 0")
        # Set the control mode to external level. The shutter will be open as
        # long as the external input is high.
        self.send("SRCE 2")
        # Enable the shutter - wake from 'sleep' mode.
        if enab:
            self.send("ENAB 1")
        else:
            self.send("ENAB 0")


    def onExit(self):
        try:
            # Reset the controller to close the shutter and revert to internal
            # triggering.
            self.send("*RST")
            # Go to local mode to enable the front panel
            self.send("LCAL")
            self.connection.close()
        except:
            pass


    def onPrepareForExperiment(self, experiment):
        self.enableTrigger()


    def onCleanupAfterExperiment(self):
        # Assert shutter closed (also reverts to internal triggering).
        self.send("ASRT 0")
        self.enableTrigger()


    def setExposureTime(self, t):
        # Could set exposure on controller, but currently rely on bulb trigger
        # from a trigger source.
        pass


    def send(self, command):
        self.connection.write( (command + '\n').encode() )
        return self.connection.read_until('\n'.encode(), 0.05)
