#!/usr/bin/python
# -*- coding: UTF8   -*-
""" This module makes a retarder/rotator available to Cockpit.

The device class makes available a handler for SI experiments which
takes an integer argument in the action table that specifies the SI
angle index. Upon exmining the table, it replaces instances of this
handler with instances of whatever handler drives the analogue out-
put, having converted the angle index to the required voltage.

Copyright Mick Phillips, University of Oxford, 2015-2018.

Sample config entry:
  [polarizer]
  type: PolarizationDevice
  analogSource: dsp
  analogLine: 1
  siVoltages: 488: 0.915, 1.05, 1.23
              561: 1.32, 0.90, 1.12
              647: 1.18, 1.61, 0.97
  idleVoltage: 1.0
  offset: 0                             # in volts
  gain: 6553.6                          # in ADU per volt


  [dsp]
  type: LegacyDSP
  ...
"""
import depot
from . import device

class PolarizationDevice(device.Device):
    _config_types = {
        'idlevoltage': float,
        'offset': float,
        'gain': float,
    }

    # For use in SI experiments, should be named "SI polarizer" in config.
    # TODO - identify the polarizer some other way.
    def __init__(self, name, config={}):
        device.Device.__init__(self, name, config)


    def getHandlers(self):
        asource = self.config.get('analogsource', None)
        aline = self.config.get('analogline', None)
        offset = self.config.get('offset', 0)
        gain = self.config.get('gain', 1)
        dt = Decimal(self.config.get('settlingtime', 0.05))
        aHandler = depot.getHandler(asource, depot.EXECUTOR)

        if aHandler is None:
            raise Exception('No control source.')
        movementTimeFunc = lambda x, start, delta: (0, dt)
        handler = aHandler.registerAnalog(self, aline, offset, gain, movementTimeFunc)

        # Connect handler to analogue source to populate movement callbacks.
        handler.connectToAnalogSource(aHandler, aline, offset, gain)

        result.append(handler)
        return result


    def getHandlers(self):
        aSource = self.config.get('analogsource', None)
        aLine = self.config.get('analogline', None)
        aHandler = depot.getHandler(aSource, depot.EXECUTOR)
        if aHandler is None:
            raise Exception('No control source.')
        gain = self.config.get('gain', 1)
        offset = self.config.get('offset', 0)
        h = aHandler.registerAnalog(self, aLine, offset, gain)

        # If there are indexed positions in the config, add them to the handler.
        idlevoltage = self.config.get('idlevoltage', 0)
        voltages = {}
        for vdef in self.config.get('sivoltages', '').split('\n'):
            if vdef is '':
                continue
            key, values = vdef.strip('\n').split(':')
            voltages[key] = tuple([float(v) for v in values.split(',')])
        if not set(['default', None]).intersection(voltages):
            voltages[None] = 3 * [idlevoltage]
        h.positions = voltages
        return [h]
