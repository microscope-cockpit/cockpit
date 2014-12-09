""" Cockpit LaserPowerDevice

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
            # Default to not allowing the laser to go below 1mW.
            # Have to use try/except as hasattr does not seem to work correctly
            # for Pyro objects.
            try:
                minPower = self.nameToConnection[label].minPower()
            except:
                minPower = 1
            # These values are only available if the laser is powered up. If
            # we can't get them now, we'll get them when the light source
            # is enabled.
            maxPower = 0
            curPower = 0
            isPowered = False
            maxPower = self.nameToConnection[label].getMaxPower_mW()
            curPower = self.nameToConnection[label].getPower_mW()
            isPowered = True
            powerHandler = handlers.lightPower.LightPowerHandler(
                    label + ' power', # name
                    label, # groupName
                    {
                        'setPower': self.setLaserPower
                    },
                    light['wavelength'], 
                    minPower, maxPower, curPower,
                    light['color'],
                    isEnabled = isPowered)
            result.append(powerHandler)
            self.nameToHandler[label] = powerHandler
            self.nameToIsEnabled[label] = False
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


    ## A light source was enabled. Check if it's one of our Deepstar lasers,
    # throw an error if the laser is not powered up, and otherwise get the
    # current power levels if we don't already have them.
    def onLightSourceEnable(self, handler, isEnabled):
        label = handler.name
        if (label in self.nameToIsEnabled and
                self.nameToIsEnabled[label] == isEnabled):
            # Light source is already in the desired state; no need to do
            # anything.
            return

        # Use the group name (e.g. "488nm") instead of the
        # handler name (e.g. "488nm power").
        status = wx.ProgressDialog(parent = wx.GetApp().GetTopWindow(),
                title = "Laser power communication",
                message = "Communicating with the %s..." % handler.groupName)
        status.Show()
        
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
                    if connection.loadStatus():
                        break
                    if i != 2:
                        time.sleep(5)
                handler.setMaxPower(connection.getMaxPower_mW())
                handler.setCurPower(connection.getPower())
                handler.setEnabled(True)

            # Try to enable the laser.
            if not connection.enable():
                wx.MessageBox("I was unable to enable the %s laser. Please ensure the key is turned and the standby switch is on." % handler.name,
                        "Error: Couldn't enable laser",
                        wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
                # Disable the handler
                wx.CallAfter(handler.setEnabled, False)
                status.Destroy()
                return
        else:
            if connection.getIsOn():
                # Disable the laser.
                connection.disable()
        status.Destroy()
        self.nameToIsEnabled[label] = isEnabled


    ## Set the power of a Deepstar laser.
    def setLaserPower(self, name, val):
        label = name.strip(' power')
        self.nameToConnection[label].setPower_mW(val)


