import depot
from . import deviceHandler

import events


## This handler mostly just handles setting up incoming communications
# from other programs.
class ServerHandler(deviceHandler.DeviceHandler):
    ## callbacks must include the following functions:
    # - register(func): Registers the function to be called when our
    #   owner receives incoming requests from outside on a specific
    #   port that we decide.
    # - unregister(func): Stops the provided function from receiving
    #   outside events.
    def __init__(self, name, groupName, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False,
                callbacks, depot.SERVER)
        

    ## Register a new function.
    def register(self, func, localIp = None):
        return self.callbacks['register'](func, localIp)


    ## Unregister a function, so it stops getting called.
    def unregister(self, func):
        return self.callbacks['unregister'](func)
