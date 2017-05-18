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
import threading
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
        ## Map names to asynchronous connections
        self.nameToAsync = {}
        ## Maps LightPower names to whether or not the corresponding
        # LightSource handler is currently enabled.
        self.nameToIsEnabled = {}
        events.subscribe('light source enable', self.onLightSourceEnable)
        ## A lock on handlers.
        self.hLock = threading.Lock()
        ## A thread to poll current laser powers.
        # Adding a single thread here to update all laser powers.
        # The alternative is to have one thread per handler, which gives
        # increased overhead for little to no gain.
        self.pollThread = threading.Thread(target=self._pollPower)
        self.pollThread.Daemon = True
        self.pollThread.start()


    def _pollPower(self):
        # Use asyncrhonous proxies so that comms delays occur in parallel.
        while True:
            asyncs = self.nameToAsync
            with self.hLock:
                powers = {}
                setPoints = {}
                for name, async in asyncs.iteritems():
                    try:
                        # Fetch current powers.
                        powers[name] = async.getPower_mW()
                        setPoints[name] = async.getSetPower_mW()
                    except Pyro4.errors.PyroError:
                        pass
            # Wait for all calls to return.
            for p in powers.itervalues():
                p.wait()
            for s in setPoints.itervalues():
                s.wait()
            with self.hLock:
                for name, h in self.nameToHandler.iteritems():
                    if name in powers:
                        try:
                            power = float(powers[name].value)
                        except:
                            # Got junk back.
                            power = None
                    else:
                        power = None
                    if name in setPoints:
                        try:
                            setPoint = float(setPoints[name].value)
                        except:
                            # Got junk back.
                            setPoint = None
                    else:
                        setPoint = None
                    h.setCurPower(power)
                    h.powerSetPoint = setPoint
                    # Populate maxPower if not already set.
                    if not h.maxPower:
                        maxPower = self.nameToConnection[name].getMaxPower_mW()
                        try:
                            h.setMaxPower(maxPower)
                            h.setMinPower(maxPower / h.numPowerLevels)
                        except:
                            pass
            time.sleep(0.1)


    ## Provide a LightPower handler for each of the lasers. The DSP
    # provides the LightSource handlers.
    def getHandlers(self):
        # Do not update dict if it is locked by _pollPower
        self.hLock.acquire()
        result = []
        #self.powerControl = depot.getDevice(devices.powerButtons)
        for label, light in self.lights.items():
            uri = 'PYRO:%s@%s:%d' % (light['device'], self.ipAddress, light['port'])
            # Create a synchronous proxy
            self.nameToConnection[label] = Pyro4.Proxy(uri)
            # Create an asynchronous proxy
            self.nameToAsync[label] = Pyro4.Proxy(uri)
            self.nameToAsync[label]._pyroAsync()
            # If the light config has minPower, use that, otherwise default to 1mW.
            minPower = light.get('minPower') or 1
            # Just set maxPwer and curPower to zero.
            # Reading them here only works if the laser is on, delays startup,
            # and _pollPower will update these soon enough, anyway.
            curPower = 0
            maxPower = 0
            isPowered = False
            isPowered = self.nameToConnection[label].isAlive()
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
        self.hLock.release()
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
    #@util.threads.callInNewThread
    @util.threads.locked
    def setLaserPower(self, name, val):
        label = name.strip(' power')
        if label in self.nameToConnection:
            self.nameToConnection[label].setPower_mW(val)
