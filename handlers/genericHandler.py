import deviceHandler
import depot



## This class stands in for arbitrary devices that don't need any particular
# special abilities. Mostly it gives Devices objects they can shove into the
# DeviceDepot and refer to in experiments.
class GenericHandler(deviceHandler.DeviceHandler):
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks={}):
        deviceHandler.DeviceHandler.__init__(self,
                name, groupName, isEligibleForExperiments,
                callbacks=callbacks, deviceType = depot.GENERIC_DEVICE)
