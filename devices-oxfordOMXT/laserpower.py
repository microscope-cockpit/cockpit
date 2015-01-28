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
#import devices.powerButtons ## Oxford doesn't have powerButtons.
import events
import handlers.lightPower
import handlers.lightSource

CLASS_NAME = 'LaserPowerDevice'
SUPPORTED_LASERS = ['Deepstar',]# 'cobalt']

from config import config, LIGHTS

class LaserPowerDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## IP address of the computer which talks to the lasers.
        self.ipAddress = config.get('lights', 'ipAddress')
        
        ## Map wavelength to tuple(port, laser type).
        self.wavelengthToDevice = {}
        for key, light in LIGHTS.iteritems():
            laserType = light.get('device', '').capitalize()
            if laserType in SUPPORTED_LASERS:
                self.wavelengthToDevice.update(\
                    {light['wavelength']: (light['port'], laserType, light['color'])})

        ## The PowerButtons Device, which we need to communicate with.
        self.powerControl = None

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
        for wavelength, (port, laserType, color) in self.wavelengthToDevice.items():
            label = '%d Laser power' % wavelength
            uri = 'PYRO:pyro%d%sLaser@%s:%d' % (wavelength, laserType,
                                                self.ipAddress, port)
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
            #if self.powerControl.getIsDevicePowered('%d Deepstar' % wavelength):
            #    maxPower = self.nameToConnection[label].getMaxPower()
            #    curPower = self.nameToConnection[label].getPower()
            #    isPowered = True
            maxPower = self.nameToConnection[label].getMaxPower_mW()
            curPower = self.nameToConnection[label].getPower_mW()
            isPowered = True
            powerHandler = handlers.lightPower.LightPowerHandler(
                    label, '%d Deepstar' % wavelength,
                    {
                        'setPower': self.setLaserPower
                    },
                    wavelength, minPower, maxPower, curPower,
                    color,
                    isEnabled = isPowered)
            result.append(powerHandler)
            self.nameToHandler[powerHandler.name] = powerHandler
            self.nameToIsEnabled[powerHandler.name] = False
        return result
                        

    ## A light source was enabled. Check if it's one of our Deepstar lasers,
    # throw an error if the laser is not powered up, and otherwise get the
    # current power levels if we don't already have them.
    def onLightSourceEnable(self, handler, isEnabled):
        powerName = handler.name + ' power'
        if powerName not in self.nameToConnection:
            # Not a Deepstar laser.
            return

        if (powerName in self.nameToIsEnabled and
                self.nameToIsEnabled[powerName] == isEnabled):
            # Light source is already in the desired state; no need to do
            # anything.
            return

        # Use the group name (e.g. "488 Deepstar") instead of the
        # handler name (e.g. "488 Deepstar power").
        status = wx.ProgressDialog(parent = wx.GetApp().GetTopWindow(),
                title = "Deepstar communication",
                message = "Communicating with the %s..." % handler.groupName)
        status.Show()
        
        if not self.powerControl.getIsDevicePowered(handler.name):
            if isEnabled:
                # Laser isn't turned on, so it can't actually be enabled.
                wx.MessageBox("The %s laser is not powered on. Please turn it on using the Power Buttons program." % handler.name,
                        "Error: Device not powered",
                        wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
                # Disable the handler
                wx.CallAfter(handler.setEnabled, False)
            # In either case, nothing to be done here.
            status.Destroy()
            return

        connection = self.nameToConnection[powerName]
        if isEnabled:
            # Ensure that the LightPower handler has appropriate settings.
            handler = self.nameToHandler[powerName]
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
        self.nameToIsEnabled[powerName] = isEnabled


    ## Set the power of a Deepstar laser.
    def setLaserPower(self, name, val):
        self.nameToConnection[name].setPower_mW(val)


