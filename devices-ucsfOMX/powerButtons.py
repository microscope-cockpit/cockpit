import device
import handlers.powerControl

import Pyro4

CLASS_NAME = 'PowerButtonsDevice'


## This Device is mostly just for letting us power devices off at the ends of
# experiments, and for checking if the diffuser wheel is on.
class PowerButtonsDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## IP address for the power buttons program
        self.ipAddress = '192.168.12.2'
        ## Port for the power buttons program.
        self.port = 7770
        ## Connection to the power buttons program
        self.connection = None


    def initialize(self):
        self.connect()


    ## (Re)-establish a connection to the power buttons program.
    def connect(self):
        self.connection = Pyro4.Proxy(
                'PYRO:pyroPowerButtonsList@%s:%d' % (self.ipAddress, self.port))


    def getHandlers(self):
        # One handler for the diffuser wheel, one for the other devices.
        # \todo This is pretty hackish since we don't actually tell the
        # truth when powering off the diffuser or when checking the status
        # of the other devices; each handler does only one thing.
        result = []
        result.append(handlers.powerControl.PowerControlHandler(
                "Diffuser wheel power", "power buttons",
                # We don't allow separately disabling the diffuser wheel.
                {'disable': lambda a: False,
                 'getIsOn': self.getIsDiffuserWheelOn}))
        result.append(handlers.powerControl.PowerControlHandler(
                "All devices power", "power buttons",
                {'disable': self.disableAllDevices,
                # We don't actually care if other devices are on.
                 'getIsOn': lambda a: True}))
        return result


    ## Get if the diffuser wheel is on or not.
    def getIsDiffuserWheelOn(self, name):
        self.connect()
        return self.connection.get_is_diffuser_on()


    ## Get if a device connected to the SerialBootBar is on or not.
    def getIsDevicePowered(self, name):
        self.connect()
        return self.connection.get_is_device_powered(name)


    ## Turn everything off.
    def disableAllDevices(self, name):
        self.connect()
        return self.connection.turn_all_off()
