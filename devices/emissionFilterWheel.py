""" Module to control ThorLabs fw102c filter wheels.

This module makes one or more filter wheels available to 
cockpit to control emission filters.

Copyright 2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import depot
import device
import events
from collections import namedtuple
from config import config
import re
import wx

CLASS_NAME = 'FilterWheelManager'
CONFIG_NAME = 'emission wheel'
CONFIG_DELIMETERS = '[,;:\-]+ ?'

__DRAWERHANDLER__ = None

Filter = namedtuple('Filter', 'dye, wavelength')


class FilterWheelManager(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # Must be initialized after the drawer.
        self.priority = 500
        names = [s for s in config.sections() if s.startswith(CONFIG_NAME)]
        if not names:
            self.isActive = False
            return
        self.isActive = True
        self.wheels = []
        for name in names:
            self.wheels.append(FilterWheelDevice(name))


    def initialize(self):
        for w in self.wheels:
            w.initialize()


    def finalizeInitialization(self):
        for w in self.wheels:
            w.finalizeInitialization()


class FilterWheelDevice(device.Device):
    def __init__(self, name):
        self.name = name
        self.cameraNames = []
        self.filters = []
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.pollFunction)
        self.curPosition = None


    def finalizeInitialization(self):
        # The drawer is initialized by now.
        global __DRAWERHANDLER__
        __DRAWERHANDLER__ = depot.getHandlersOfType(depot.DRAWER)[0]
        print '__DRAWERHANDLER__: %s' % __DRAWERHANDLER__
        # Cameras also initialized by now.
        if config.has_option(self.name, 'camera'):
            cameras = [config.get(self.name, 'camera')]
        elif config.has_option(self.name, 'cameras'):
            cameras = re.split(CONFIG_DELIMETERS, config.get(self.name, 'cameras'))
        else:
            raise Exception('%s: no camera(s) defined for %s' % (CLASS_NAME, self.name))
        self.cameraNames = [c.name for c in depot.getHandlersOfType(depot.CAMERA)
                                if c.name.lower() in cameras]
        # Update the drawer.
        self.updateDrawer()


    def initialize(self):
        # Read config to populate filters.
        numSlots = config.getint(self.name, 'slots')
        self.filters = []
        for i in range(1, numSlots+1):
            if config.has_option(self.name, str(i)):
                filterStr = config.get(self.name, str(i))
                f = Filter(*re.split(CONFIG_DELIMETERS, filterStr))
            else:
                f = Filter(None, None)
            self.filters.append(f)
        # Get the current position.
        self.curPosition = self.getPosition()
        # Start the timer that will detect manual position changes.
        self.timer.Start(1000)


    def setFilter(self, filter):
        # Move to specified filter.
        pass


    def getPosition(self):
        # Fetch the current position.
        return 0
        pass


    def setPosition(self, position):
        # Move to specified position.
        pass


    def updateDrawer(self):
        h = __DRAWERHANDLER__
        f = self.filters[self.curPosition]
        for camera in self.cameraNames:
            h.changeFilter(camera, f.dye, f.wavelength)
        events.publish("drawer change", h)


    def pollFunction(self, evt):
        lastPosition = self.curPosition
        self.curPosition = self.getPosition()
        if lastPosition != self.curPosition:
            self.updateDrawer()
