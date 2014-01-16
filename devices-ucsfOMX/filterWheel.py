import device
import handlers.lightFilter

import Pyro4

CLASS_NAME = 'FilterWheelDevice'

## Table that maps ND filter settings to fraction of permitted light. 
# Values are from Lukman's table of empirically-derived filtration rates. 
# lineTransmissivity[i][j][k]:
# - i: Which laser (488, 560)
# - j: Current global ND position (index into [100, 50, 12, 6, 1])
# - k: Current specific ND position (filter amount depends on laser)
# Note that this is not simply a linear combination of the global and local
# filter amounts! There are significantly nonlinear responses here (e.g. 
# a stricter global position can actually result in *more* light for the 405
# laser...). 
lineTransmissivity = [None] * 2
# 488
lineTransmissivity[0] = [
        [1, 0.402, 0.0774, 0.00652, 0.00141],
        [0.467, 0.188, 0.0361, 0.00304, 0.000659],
        [0.112, 0.0448, 0.00863, 0.000728, 0.000158],
        [0.06, 0.0241, 0.00463, 0.000391, 0.0000848],
        [0.0102, 0.00409, 0.000787, 0.0000663, 0.0000144],
]
# 560
lineTransmissivity[1] = [
        [1, 0.0818, 0.00913, 0.00183],
        [0.467, 0.0381, 0.00427, 0.000852],
        [0.153, 0.0125, 0.00139, 0.000279],
        [0.218, 0.0179, 0.00199, 0.000398],
        [0.0816, 0.00668, 0.000744, 0.000149],
]


class FilterWheelDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Maps wheel names to (IP address, port) tuples for the programs
        # controlling those wheels.
        self.nameToConnectInfo = {
                'MainNDWheel': ('192.168.12.31', 7769),
                '488NDWheel': ('192.168.12.2', 7768),
                '560NDWheel': ('192.168.12.31', 7771),
        }
        ## Maps wheel names to connections to the programs for those wheels.
        self.nameToConnection = {}
        ## Maps handler names to wheel program names. Arguably not needed,
        # but the display names in the program are nicer than the service
        # names, and I don't really want to rename the services.
        self.handlerNameToServiceName = {
                'Global ND': 'MainNDWheel',
                '488 ND': '488NDWheel',
                '560 ND': '560NDWheel',
        }

        
    def initialize(self):
        for name, (ipAddress, port) in self.nameToConnectInfo.iteritems():
            self.nameToConnection[name] = Pyro4.Proxy(
                    'PYRO:%s@%s:%s' % (name, ipAddress, port))

        
    def getHandlers(self):
        # HACK: put the global ND filter under the "ambient light" group
        # so that the UI puts the "room light" exposure time control
        # vertically under it.
        result = [handlers.lightFilter.LightFilterHandler(
                "Global ND", "Ambient light",
                {'setPosition': self.setFilterPosition}, None, 
                [1, .5, .1, .02, .001], (255, 255, 0), 
                0, 0, globalIndex = 0)]
        for i, (wavelength, color) in enumerate([
                (488, (40, 130, 180)), (560, (40, 230, 40))]):
            result.append(handlers.lightFilter.LightFilterHandler(
                "%d ND" % wavelength, "%d light" % wavelength,
                {'setPosition': self.setFilterPosition},
                wavelength, lineTransmissivity[i], color, 0, 1)
            )
        return result


    ## Move the specified filter wheel to the specified position.
    def setFilterPosition(self, filterName, position):
        serviceName = self.handlerNameToServiceName[filterName]
        connection = self.nameToConnection[serviceName]
        command = 'pos=%d\r' % (position + 1)
        connection.write(command)
        response = connection.read(len(command))
        if command != response:
            # Clear any output from the wheel.
            connection.read(100)
            raise RuntimeError("Unexpected response from %s wheel: [%s] (expected [%s])" % (filterName, response, command))
        # Read the prompt.
        response = connection.read(2)
        if response != '> ':
            # Clear any output from the wheel.
            connection.read(100)
            raise RuntimeError("Unexpected response from %s wheel: [%s] (expected [> ])" % (filterName, response))

        
