## This module provides a Device that is used to take images with our dummy
# camera. Ordinarily this functionality would be covered by some kind of 
# signal source (e.g. an FPGA or DSP card). 

import depot
import device
import events
import handlers.imager

CLASS_NAME = 'DummyImagerDevice'



class DummyImagerDevice(device.Device):
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

