import depot
import device
import handlers.lightSource

CLASS_NAME = 'DummyLightsDevice'



class DummyLightsDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self, 'dummy lights')
        ## Maps lightsource names to their exposure times.
        self.nameToExposureTime = dict()
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')        
        self.deviceType = 'light source'

    def getHandlers(self):
        result = []
        for label, wavelength in [('405 shutter', 405),
                ('488 shutter', 488), 
                ('640 shutter', 640)]:
            # Set up lightsource handlers. Default to 100ms exposure time.
            handler = handlers.lightSource.LightHandler(
                label, "%s light source" % label, 
                {'setEnabled': lambda *args: None,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime}, wavelength, 100)
            self.nameToExposureTime[handler.name] = 100
            result.append(handler)
        return result


    ## Change the exposure time for a light source.
    def setExposureTime(self, name, time):
        self.nameToExposureTime[name] = time


    ## Get the exposure time for a light source.
    def getExposureTime(self, name):
        return self.nameToExposureTime[name]

