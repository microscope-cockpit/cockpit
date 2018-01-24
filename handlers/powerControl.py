import depot
from . import deviceHandler


## This handler provides the ability to check if a device is running, and
# to power devices off.
class PowerControlHandler(deviceHandler.DeviceHandler):
    ## callbacks must include the following:
    # - disable(name): Turn the device off.
    # - getIsOn(name): Return True if the device is currently on.
    def __init__(self, name, groupName, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False,
                callbacks, depot.POWER_CONTROL)


    ## Power the device off.
    def disable(self):
        return self.callbacks['disable'](self.name)


    ## Return True if the device is on, False otherwise.
    def getIsOn(self):
        return self.callbacks['getIsOn'](self.name)
