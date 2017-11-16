import depot
import deviceHandler

## This handler is for generic positioning devices that can move along a 
# single axis, and are not used for stage/sample positioning. Use the
# StagePositionerHandler for positioners that move the sample around.
class GenericPositionerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - moveAbsolute(name, position): Move to the given position, in whatever
    #   units are appropriate.
    # - moveRelative(name, delta): Move by the specified delta, again in 
    #   whatever units are appropriate. 
    # - getPosition(name): Get the current position.
    # Additionally, if the device is eligible for experiments, it needs to 
    # have these functions:
    # - getMovementTime(name, start, stop): return the movement time and 
    #   stabilization time needed to go from <start> to <stop>.
    # \todo Add motion limits.
    
    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                isEligibleForExperiments, callbacks, 
                depot.GENERIC_POSITIONER)


    ## Handle being told to move to a specific position.
    def moveAbsolute(self, pos):
        self.callbacks['moveAbsolute'](pos)


    ## Handle being told to move by a specific delta.
    def moveRelative(self, delta):
        self.callbacks['moveRelative'](delta)


    ## Retrieve the current position.
    def getPosition(self):
        return self.callbacks['getPosition']()


    ## Get the movement and stabilization time needed to perform the specified
    # motion, in milliseconds.
    def getMovementTime(self, start, stop):
        #return self.callbacks['getMovementTime'](self.name, start, stop)
        return self.getDeltaMovementTime(stop - start)


    @cached
    def getDeltaMovementTime(self, delta):
        return self.callbacks['getMovementTime'](0., delta)