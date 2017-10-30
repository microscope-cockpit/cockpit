import depot
import deviceHandler

## This handler is a mix-in for handlers that abstract an analogue line.
class AnalogueHandlerMixin(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - getLineHandler(): return the analogue line handler.
    
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                isEligibleForExperiments, callbacks, 
                depot.GENERIC_DEVICE)


    ## Retrieve the real analogue line handler.
    def getLineHandler(self):
        return self.callbacks['getLineHandler']()