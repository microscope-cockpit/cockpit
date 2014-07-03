import device
import handlers.lightFilter

import Pyro4

CLASS_NAME = 'FilterWheelDevice'

## Table that maps ND filter settings to fraction of permitted light. 
# Values are from Lukman's table of empirically-derived filtration rates. 
# lineTransmissivity[i][j][k]:
# - i: Which laser (405, 560, 640)
# - j: Current global ND position (index into [100, 50, 12, 6, 1])
# - k: Current specific ND position (filter amount depends on laser)
# Note that this is not simply a linear combination of the global and local
# filter amounts! There are significantly nonlinear responses here (e.g. 
# a stricter global position can actually result in *more* light for the 405
# laser...). 
#IMD 20130308 hack to take out everything but one light source

lineTransmissivity = [None] * 1
# 488
lineTransmissivity[0] = [
        [100.0, 50.0, 10.0, 5.0, 1.0, 0.5],
]

# Oxford deepstar lasers, index so we can call enable and disable
# on the deepstar laser when selected in the interface
deepstarLasers = ['488']

### 560
##lineTransmissivity[1] = [
##        [1, 0.0818, 0.00913, 0.00183],
##        [0.467, 0.0381, 0.00427, 0.000852],
##        [0.153, 0.0125, 0.00139, 0.000279],
##        [0.218, 0.0179, 0.00199, 0.000398],
##        [0.0816, 0.00668, 0.000744, 0.000149],
##]
### 640
##lineTransmissivity[2] = [
##        [1, 0.104, 0.0132, 0.00164],
##        [0.944, 0.0986, 0.0125, 0.00154],
##        [1.16, 0.121, 0.0154, 0.0019],
##        [0.911, 0.0951, 0.0121, 0.00149],
##        [1, 0.105, 0.0133, 0.00164],
##]


class FilterWheelDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Maps wheel names to (IP address, port) tuples for the programs
        # controlling those wheels.
        self.nameToConnectInfo = {
                'pyro488DeepstarLaser': ('172.16.0.21', 7776),
#                '405NDWheel': ('192.168.12.31', 7768),
#                '560NDWheel': ('192.168.12.31', 7771),
#                '640NDWheel': ('192.168.12.31', 7772),
        }
        ## Maps wheel names to connections to the programs for those wheels.
        self.nameToConnection = {}
        ## Maps handler names to wheel program names. Arguably not needed,
        # but the display names in the program are nicer than the service
        # names, and I don't really want to rename the services.
        self.handlerNameToServiceName = {
                '488 ND': 'pyro488DeepstarLaser',
#                '405 ND': '405NDWheel',
#                '560 ND': '560NDWheel',
#                '640 ND': '640NDWheel',
        }


        
    def initialize(self):
        import util.logger
        for name, (ipAddress, port) in self.nameToConnectInfo.iteritems():
            self.nameToConnection[name] = Pyro4.Proxy(
                    'PYRO:%s@%s:%d' % (name, ipAddress, port))
            #IMD 05-04-2013 Hack to get laser talking
            self.nameToConnection[name].enable()
        
    def getHandlers(self):
        # HACK: put the global ND filter under the "room light" group
        # so that the UI puts the "room light" exposure time control
        # vertically under it.
     #   result = [handlers.lightFilter.LightFilterHandler(
     #            "Room light source",
     #           {'setPosition': self.setFilterPosition}, None, 
     #           [1, .5, .1, .02, .001], (255, 255, 0), 
     #           0, 0, globalIndex = 0)]
        result = []
        for i, (wavelength, color) in enumerate([
                (488, (30, 30, 230))]):
                #,
                #(560, (40, 230, 40)), (640, (255, 40, 40))
                #]):
            result.append(handlers.lightFilter.LightFilterHandler(
                "%d ND" % wavelength, "%d light source" % wavelength,
                {'setPosition': self.setFilterPosition},
                wavelength, lineTransmissivity[i], color,4 , 0) # 4 is 1% transmission, good starting value
                          
            )
        for wavelength in enumerate([deepstarLasers]):
            print "deepstar wavelength",wavelength
        return result


    ## Move the specified filter wheel to the specified position.
    def setFilterPosition(self, filterName, position):
        serviceName = self.handlerNameToServiceName[filterName]
        connection = self.nameToConnection[serviceName]
        response=connection.setPower(lineTransmissivity[0][0][position]/100)
        print "setpower =",response
        
##        if command != response:
##            # Clear any output from the wheel.
##            connection.read(100)
##            raise RuntimeError("Unexpected response from %s wheel: [%s] (expected [%s])" % (filterName, response, command))
##        # Read the prompt.
##        response = connection.read(2)
##        if response != '> ':
##            # Clear any output from the wheel.
##            connection.read(100)
##            raise RuntimeError("Unexpected response from %s wheel: [%s] (expected [> ])" % (filterName, response))

        
