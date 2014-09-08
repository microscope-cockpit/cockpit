## This module provides a Device that is used to take images with our dummy
# camera. Ordinarily this functionality would be covered by some kind of 
# signal source (e.g. an FPGA or DSP card). 

import depot
import device
import events
import handlers.imager

CLASS_NAME = 'DummyImagerDevice'


class DummyImagerDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')
        self.deviceType = 'imager'


    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        result.append(handlers.imager.ImagerHandler(
            "Dummy imager", "imager",
            {'takeImage': self.takeImage}))
        return result


    ## Take an image. Normally we'd coordinate camera and light trigger signals
    # at this point, but the dummy system has no hardware so we just pretend.
    def takeImage(self):
        events.publish("dummy take image")


    ## As an example, this module supports the ability to be dynamically
    # reloaded via the depot.reloadModule() function. These two functions
    # need to be implemented for this to work properly.
    def shutdown(self):
        pass


    ## Receive our old handlers, and update their callbacks to refer to us
    # instead of to the old device.
    def initFromOldDevice(self, oldDevice, handlers):
        for handler in handlers:
            if handler.name == 'Dummy imager':
                handler.callbacks = {'takeImage': self.takeImage}

