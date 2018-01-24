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

This is a base shutter device with dummy methods for testing.

"""
import re
import depot
from . import device
import events
from handlers.lightSource import LightHandler

class ShutterDevice(device.Device):
    def __init__(self, name, config={}):
        device.Device.__init__(self, name, config)
        lights = config.get('lights', None)
        if lights:
            self.lights = re.split('[,;: ]\s*', lights)
        else:
            self.lights = None


    def finalizeInitialization(self):
        ## Replace lights strings with their handlers.
        handlers = []
        for name in self.lights:
            h = depot.getHandler(name, depot.LIGHT_TOGGLE)
            if h:
                handlers.append(h)
        self.lights = handlers
        # Register this shutter with the LightHandler class.
        LightHandler.addShutter(self, self.lights)


    def initialize(self):
        pass


    def performSubscriptions(self):
            events.subscribe('prepare for experiment',
                            self.onPrepareForExperiment)
            events.subscribe('experiment complete',
                            self.onCleanupAfterExperiment)
            events.subscribe('light source enable', self.onLightSourceEnable)


    def enableTrigger(self, enable=True):
        if enable:
            print("Shutter %s enabled." % self.name)
        else:
            print("Shutter %s disabled." % self.name)


    def onLightSourceEnable(self, handler, enab):
        if enab and handler in self.lights:
            # One of our lights has been enabled.  Make sure that we respond to triggers.
            self.enableTrigger()
        elif not enab and not any([l.getIsEnabled() for l in self.lights]):
            # All of our lights are disabled.
            self.enableTrigger(False)


    def setExposureTime(self, t):
        print("Shutter %s exposure time set to %s." % (self.name, t))


    def onPrepareForExperiment(self, experiment):
        self.enableTrigger()


    def onCleanupAfterExperiment(self):
        pass