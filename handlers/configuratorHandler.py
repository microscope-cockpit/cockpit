import depot
import deviceHandler


## This handler stores various configuration information about the microscope
# that isn't directly associated with any specific device.
class ConfiguratorHandler(deviceHandler.DeviceHandler):
    ## \param config A dictionary of configuration information. Should include
    # the following keys:
    # - slideAltitude Approximate Z altitude at which slides are in focus.
    # - slideTouchdownAltitude Approximate Z altitude at which the immersion
    #   fluid will make contact between the objective and a slide.
    # - dishAltitude Approximate Z altitude at which dishes are in focus.
    # - dataDirectory Path to the directory in which user data should be stored.
    # - logDirectory Path to the directory in which program log files should
    #   be stored.
    # - configDirectory Path to the directory in which user config should be 
    #   stored.
    def __init__(self, name, groupName, callbacks, config):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False, 
                callbacks, depot.CONFIGURATOR)
        self.config = config


    ## Retrieve the specified value from our config.
    def getValue(self, key):
        if key not in self.config:
            raise KeyError("Invalid config key [%s]" % key)
        return self.config[key]
