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


""" Cockpit device for SRS SR470 shutter controller.

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
