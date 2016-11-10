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

Sample config entry:

    [emission wheel 1]
    ipAddress = 127.0.0.1
    port = 8002
    id = dummy
    cameras = dummy camera 1, dummy camera 2
    slots = 6
    1 = GFP, 525
    2 = TRITC, 600
"""
import depot
import device
import events
import gui
from collections import namedtuple
from config import config
import Pyro4
import re
import threading
import time
import util
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
        # One timer keeps all displays current.
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.updateUI)
        # One thread polls all wheels to keep positions current. We don't do
        # this in updateUI because delays could cause the UI thread to block.
        self.pollThread = threading.Thread(target=self.pollFunction)


    def initialize(self):
        for w in self.wheels:
            w.initialize()


    def finalizeInitialization(self):
        for w in self.wheels:
            w.finalizeInitialization()
        # Start the polling thread.
        self.pollThread.start()


    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetDoubleBuffered(True)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(parent=self.panel, label='Filters')
        sizer.Add(label)
        for w in self.wheels:
            display = w.makeUI(self.panel)
            sizer.Add(display)
        self.panel.SetSizerAndFit(sizer)
        self.timer.Start(1000)
        return self.panel


    def pollFunction(self):
        while True:
            for w in self.wheels:
                try:
                    w.getPosition()
                except:
                    continue
            time.sleep(1)


    def updateUI(self, evt=None):
        for w in self.wheels:
            w.updateUI()


class FilterWheelDevice(device.Device):
    def __init__(self, name):
        self.name = name
        self.displayName = name.replace(CONFIG_NAME, '').lstrip()
        self.connection = None
        self.cameraNames = []
        self.filters = []
        self.curPosition = None
        self.lastPosition = None


    def finalizeInitialization(self):
        # The drawer is initialized by now.
        global __DRAWERHANDLER__
        __DRAWERHANDLER__ = depot.getHandlersOfType(depot.DRAWER)[0]
        # Cameras also initialized by now.
        if config.has_option(self.name, 'camera'):
            cameras = [config.get(self.name, 'camera')]
        elif config.has_option(self.name, 'cameras'):
            cameras = re.split(CONFIG_DELIMETERS, config.get(self.name, 'cameras'))
        else:
            raise Exception('%s: no camera(s) defined for %s' % (CLASS_NAME, self.name))
        self.cameraNames = [c.name for c in depot.getHandlersOfType(depot.CAMERA)
                                if c.name.lower() in cameras]


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
        # Connect to the device.
        ipAddress = config.get(self.name, 'ipAddress')
        port = config.getint(self.name, 'port')
        wheelId = config.get(self.name, 'id')
        uri = "PYRO:%s@%s:%d" % (wheelId, ipAddress, port)
        self.remote = Pyro4.Proxy(uri)


    def getPosition(self):
        # Fetch the current position.
        self.curPosition = self.remote.getPosition()
        return self.curPosition


    @util.threads.callInNewThread
    def setPosition(self, position):
        # Move to specified position.
        self.remote.setPosition(position)


    def updateDrawer(self):
        h = __DRAWERHANDLER__
        f = self.filters[self.curPosition-1]
        for camera in self.cameraNames:
            h.changeFilter(camera, f.dye, f.wavelength)
        events.publish("drawer change", h)


    def updateUI(self):
        if self.lastPosition != self.curPosition:
            self.updateDrawer()
            dye = self.filters[self.curPosition-1].dye
            wavelength = self.filters[self.curPosition-1].wavelength or None
            if dye:
                self.display.SetLabel('%s\n%s (%s)' % (self.displayName, dye, wavelength))
            else:
                self.display.SetLabel('%s\nno filter' % self.displayName)


    def makeUI(self, parent):
        self.display = gui.toggleButton.ToggleButton(
                        parent=parent, label='', isBold=False)
        self.display.Bind(wx.EVT_LEFT_DOWN, self.menuFunc)
        return self.display


    def menuFunc(self, evt=None):
        items = ["%d: %s (%s)" % (i+1, f.dye, f.wavelength) for i, f in enumerate(self.filters)]
        menu = gui.device.Menu(items, self.menuCallback)
        menu.show(evt)


    def menuCallback(self, index, item):
        position, dye = item.split(': ')
        self.setPosition(int(position))
