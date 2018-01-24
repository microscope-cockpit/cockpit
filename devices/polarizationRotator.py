#!/usr/bin/python
# -*- coding: UTF8   -*-
""" This module makes a retarder/rotator available to Cockpit.

The device class makes available a handler for SI experiments which
takes an integer argument in the action table that specifies the SI
angle index. Upon exmining the table, it replaces instances of this
handler with instances of whatever handler drives the analogue out-
put, having converted the angle index to the required voltage.

Copyright Mick Phillips, University of Oxford, 2015.
"""
import depot
from . import device
import re

DECIMAL_PAT = '(?:\d+(?:\.\d*)?|\.\d+)'
CALIB_PAT = '\s*(\S+)(?:[\s:,;]+)(%s(?:.*))+' % DECIMAL_PAT


class PolarizationDevice(device.Device):
    _config_types = {
        'idlevoltage': float,
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
        if 'sivoltages' in self.config:
            # Parse config entry; use empty environment to avoid code injection problems.
            vstr = re.sub('\n|\t|  +', '', self.config['sivoltages'])
            voltages = eval(vstr, {'__builtins__': {}, })
            if None not in voltages and 'default' not in voltages:
                voltages[None] = 3 * [idlevoltage]
        else:
            voltages = 3* [idlevoltage]
        h.positions = voltages
        return [h]
