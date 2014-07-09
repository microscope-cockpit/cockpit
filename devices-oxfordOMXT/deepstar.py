import Pyro4
import time
import wx

import depot
import device
import devices.powerButtons
import events
import handlers.lightPower
import handlers.lightSource

CLASS_NAME = 'DeepstarDevice'


## Maps wavelength to color used to represent that wavelength.
WAVELENGTH_TO_COLOR = {
    405: (180, 30, 230),
    488: (40, 130, 180),
    640: (255, 40, 40)
}



## This Device handles communications with the Deepstar lasers. It doesn't
# create any LightSource handlers (those are created by the DSPDevice), but
# it does create the LightPower handlers.
class DeepstarDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## IP address of the Drill computer, which handles Deepstar lasers.
        self.drillAddress = '192.168.12.31'
        ## Ports to use to connect to Deepstar control software.
        self.wavelengthToPort = {
            405: 7777, 488: 7776, 640: 7775
        }
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


    ## Provide a LightPower handler for each of the Deepstar lasers. The DSP
    # provides the LightSource handlers.
    def getHandlers(self):
        result = []
        self.powerControl = depot.getDevice(devices.powerButtons)
        for wavelength in [405, 488, 640]:
            label = '%d Deepstar power' % wavelength
            uri = 'PYRO:pyro%dDeepstarLaser@%s:%d' % (wavelength, self.drillAddress, self.wavelengthToPort[wavelength])
            self.nameToConnection[label] = Pyro4.Proxy(uri)
            # Default to not allowing the laser to go below .1mW.
            minPower = .1
            # These values are only available if the laser is powered up. If
            # we can't get them now, we'll get them when the light source
            # is enabled.
            maxPower = 0
            curPower = 0
            isPowered = False
            if self.powerControl.getIsDevicePowered('%d Deepstar' % wavelength):
                maxPower = self.nameToConnection[label].getMaxPower()
                curPower = self.nameToConnection[label].getPower()
                isPowered = True
            powerHandler = handlers.lightPower.LightPowerHandler(
                    label, '%d Deepstar' % wavelength,
                    {
                        'setPower': self.setDeepstarPower
                    },
                    wavelength, minPower, maxPower, curPower,
                    WAVELENGTH_TO_COLOR[wavelength],
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
                handler.setMaxPower(connection.getMaxPower())
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
    def setDeepstarPower(self, name, val):
        self.nameToConnection[name].setPower(val)


