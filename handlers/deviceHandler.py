## A DeviceHandler acts as the interface between the GUI and the device module.
# In other words, it tells the GUI what the device does, and translates GUI
# events into commands for the device. A variety of stock DeviceHandler 
# subclasses are available for representing common types of hardware. In order
# to make your hardware accessible to the UI, you need to make a Device, and
# implement its getHandlers() method so that it returns a list of
# DeviceHandlers. 
class DeviceHandler:
    ## \param name The name of the device being controlled. This should be
    #         unique, as it is used to indicate the specific DeviceHandler
    #         in many callback functions. 
    # \param groupName The name of the group of objects this object falls
    #        under. Multiple DeviceHandlers can correspond to a single group
    #        when their purpose is similar.
    # \param callbacks Mapping of strings to functions. Each Handler has a 
    #        different selection of functions that must be filled in by the 
    #        Device that created it. Refer to the Handler's constructor.
    # \param deviceType Type of device this is; each subclass of DeviceHandler
    #        should have a distinct deviceType. Normal users don't need to 
    #        worry about this as it is provided automatically by the 
    #        DeviceHandler subclass. 
    # \param isEligibleForExperiments True if the device can be used in
    #        experiments (i.e. data collections).
    @classmethod
    def cached(cls, f):
        def wrapper(self, *args, **kwargs):
            key = (f, args, frozenset(sorted(kwargs.items())))
            # Previously, I checked for key existence and, if it wasn't
            # found, added the key and value to the cache, then returned
            # self.__cache[key]. If another thread calls reset_cache 
            # between the cache assignment and the return, this can
            # cause a KeyError, so instead I now put the result in a 
            # local variable, cache it, then return the local.
            try:
                return self.__cache[key]
            except KeyError:
                result = f(self, *args, **kwargs)
                self.__cache[key] = result
                return result
        return wrapper


    @classmethod
    def reset_cache(cls, f):
        def wrapper(self, *args, **kwargs):
            self.__cache = {}
            return f(self, *args)
        return wrapper


    def __init__(self, name, groupName, isEligibleForExperiments, callbacks, 
            deviceType):
        self.__cache = {}
        self.name = name
        self.groupName = groupName
        self.callbacks = callbacks
        self.isEligibleForExperiments = isEligibleForExperiments
        self.deviceType = deviceType


    ## Construct any necessary UI widgets for this Device to perform its job.
    # Return a WX sizer holding the result, or None if nothing is to be 
    # inserted into the parent object. 
    # \param parent The WX object that will own the UI.
    def makeUI(self, parent):
        return None


    ## Publish any necessary events to declare our initial configuration to 
    # anything that cares. At this point, all device handlers should be 
    # initialized.
    def makeInitialPublications(self):
        pass


    ## Do any final initaliaziton actions, now that all devices are set up,
    # all subscriptions have been made, and all initial publications are done.
    def finalizeInitialization(self):
        pass


    ## Return True if we can be used during experiments.
    def getIsEligibleForExperiments(self):
        return self.isEligibleForExperiments


    ## Generate a string of information that we want to save into the 
    # experiment file's header. There's limited space (800 characters) so
    # only important information should be preserved. This callback is 
    # optional; by default nothing is generated.
    def getSavefileInfo(self):
        if 'getSavefileInfo' in self.callbacks:
            return self.callbacks['getSavefileInfo'](self.name)
        return ''


    ## Do any necessary cleanup when an experiment is finished.
    # \param isCleanupFinal This boolean indicates if we're about to leap into
    #        a followup experiment. In that situation, some cleanup steps may
    #        be unnecessary and should be omitted for performance reasons.
    def cleanupAfterExperiment(self, isCleanupFinal = True):
        pass


    ## Debugging: print some pertinent info.
    def __repr__(self):
        return "<%s named %s in group %s>" % (self.deviceType, self.name, self.groupName)
