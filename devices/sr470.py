""" Cockpit device for SRS SR470 shutter controller.

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================

This is a really simple driver for the SR470 shutter controller.  For now, all
it does is make the SR470 respond to an external trigger, although it is
feasible that the shutter controller could be programmed to control exposure
timing.

Sample config entry:
  [561nm shutter]
  type: StanfordShutter
  ipAddress: 192.168.0.10
  port: 5024
  lights: 561nm
  triggerSource: dsp
  triggerLine: 3

  [dsp]
  type: LegacyDSP
  ...

"""

from . import shutter
import telnetlib

CLASS_NAME = 'StanfordShutterDevice'
CONFIG_NAME = 'sr470'

class StanfordShutter(shutter.ShutterDevice):
    def __init__(self, name, config={}):
        shutter.ShutterDevice.__init__(self, name, config)
        # Telnet connection to device
        self.connection = None


    def initialize(self):
        """ Open telnet connection and enable response to triggers. """
        self.connection = telnetlib.Telnet(self.ipAddress, self.port, timeout=5)
        self.connection.read_until('SR470 Telnet Session:')
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
        self.connection.write(command + '\n')
        return self.connection.read_until('\n', 0.05)
