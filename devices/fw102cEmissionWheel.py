""" Module to control ThorLabs fw102c filter wheels.

This module makes one or more fw102c wheels available to 
cockpiut to control emission filters.

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
from config import config, CAMERAS
import wx

CLASS_NAME = 'ThorlabsFilterWheelDevice'
CONFIG_NAME = 'fw102c'


class ThorlabsFilterWheelDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.connection = None
        self.cameraName = ''
        self.drawerHandler = {}
        self.filters = {}
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.pollFunction)
        self.timer.Start(1000)
        wx.GetTopLevelWindows()[0].Bind(wx.EVT_IDLE, self.idle)


    def idle(self, evt):
        print 'idle'



    def initialize(self):
        # Read config to populate filters.
        pass


    def setFilter(self, filter):
        # Move to specified filter.
        pass


    def getPosition(self):
        # Fetch the current position.
        pass


    def setPosition(self, position):
        # Move to specified position.
        pass


    def pollFunction(self, evt):
        print evt








