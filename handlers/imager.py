import wx

import depot
from . import deviceHandler

import events


## This handler represents any device that is capable of causing an image to 
# be taken. That's different from a camera; an imager is what triggers the 
# camera, be it an internal trigger on the camera itself or an external signal
# source like a DSP or DAQ board. 
class ImagerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - takeImage(): Cause an image to be collected.
    def __init__(self, name, groupName, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False, 
                callbacks, depot.IMAGER)


    def takeImage(self):
        self.callbacks['takeImage']()
