""" Cockpit LaserPowerDevice

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

Handles communication with Deepstar and Cobalt device (or any laser that
implements the required remote interface).  It doesn't create any LightSource
handlers (those are created by the DSP device), but it does create the 
LightPowerHandlers. """

import Pyro4
import time
import wx

import depot
import device
import events
import handlers.lightPower
import handlers.lightSource
import util.threads

CLASS_NAME = 'LaserPowerDevice'
SUPPORTED_LASERS = ['deepstar', 'cobolt']

from config import config, LIGHTS


class LaserPowerDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## IP address of the computer which talks to the lasers.
        self.ipAddress = config.get('lights', 'ipAddress')
        
        ## Map wavelength to tuple(port, laser type).
        self.lights = {}
        for label, light in LIGHTS.iteritems():
            deviceName = light.get('device', '')
            if any(deviceName.startswith(laser) for laser in SUPPORTED_LASERS):
                self.lights.update({label: light})

        ## Maps LightPower names to their handlers.
        self.nameToHandler = {}
        ## Maps LightPower names to software connections on the Drill
        # computer.
        self.nameToConnection = {}
        ## Maps LightPower names to whether or not the corresponding
        # LightSource handler is currently enabled.
        self.nameToIsEnabled = {}
        events.subscribe('light source enable', self.onLightSourceEnable)


    ## Provide a LightPower handler for each of the lasers. The DSP
    # provides the LightSource handlers.
    def getHandlers(self):
        result = []
        #self.powerControl = depot.getDevice(devices.powerButtons)
        for label, light in self.lights.items():
            uri = 'PYRO:%s@%s:%d' % (light['device'], self.ipAddress, light['port'])
            self.nameToConnection[label] = Pyro4.Proxy(uri)
            # If the light config has minPower, use that, otherwise default to 1mW.
            minPower = light.get('minPower') or 1
            # These values are only available if the laser is powered up. If
            # we can't get them now, we'll get them when the light source
            # is enabled.
            maxPower = 0
            curPower = 0
            isPowered = False
            isPowered = self.nameToConnection[label].isAlive()
            if isPowered:
                maxPower = self.nameToConnection[label].getMaxPower_mW()
                curPower = self.nameToConnection[label].getPower_mW()
            
            powerHandler = handlers.lightPower.LightPowerHandler(
                    label + ' power', # name
                    label + ' light source', # groupName
                    {
                        'setPower': self.setLaserPower
                    },
                    light['wavelength'], 
                    minPower, maxPower, curPower,
                    light['color'],
                    isEnabled = isPowered)
            result.append(powerHandler)
            self.nameToHandler[label] = powerHandler
            try:
                isEnabled = self.nameToConnection[label].getIsOn()
            except:
                isEnabled = False
            self.nameToIsEnabled[label] = isEnabled
        return result
                        

    ## Things to do when cockpit exits.
    def onExit(self):
        # Turn off the lasers.
        for name, connection in self.nameToConnection.iteritems():
            try:
                connection.disable()
                connection.onExit()
            except:
                pass


    ## A light source was enabled. Check if it's one of our lasers,
    # throw an error if the laser is not powered up, and otherwise get the
    # current power levels if we don't already have them.
    @util.threads.locked
    @util.threads.callInNewThread
    def onLightSourceEnable(self, handler, isEnabled):
        label = handler.name
        if label not in self.lights:
            # Not one of our lasers.
            return

        if (label in self.nameToIsEnabled and
                self.nameToIsEnabled[label] == isEnabled):
            # Light source is already in the desired state; no need to do
            # anything.
            return
        
        connection = self.nameToConnection[label]
        if isEnabled:
            # Ensure that the LightPower handler has appropriate settings.
            handler = self.nameToHandler[label]
            if not handler.getIsEnabled():
                # The handler was previously disabled because the laser
                # was off, so we need to load some values that were, until
                # now, unavailable.
                # Loading the device status may fail if the device was
                # only recently turned on, so we try multiple times.
                for i in xrange(3):
                    if connection.isAlive():
                        break
                    if i != 2:
                        time.sleep(5)
                handler.setMaxPower(connection.getMaxPower_mW())
                handler.setCurPower(connection.getPower_mW())
                handler.setEnabled(True)

            # Try to enable the laser.
            if not connection.enable():
                wx.MessageBox("I was unable to enable the %s laser. Please check power/standby switch, safety key state and any interlocks." % handler.name,
                        "Error: Couldn't enable laser",
                        wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
                # Disable the handler
                wx.CallAfter(handler.setEnabled, False)
                return
        else:
            if connection.getIsOn():
                # Disable the laser.
                connection.disable()
        self.nameToIsEnabled[label] = isEnabled


    ## Set the power of a supported laser.
    @util.threads.locked
    @util.threads.callInNewThread
    def setLaserPower(self, name, val):
        label = name.strip(' power')
        self.nameToConnection[label].setPower_mW(val)
