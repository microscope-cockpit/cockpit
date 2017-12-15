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
import config
import depot
import device

import decimal
import handlers.genericPositioner
import re
from config import config

DECIMAL_PAT = '(?:\d+(?:\.\d*)?|\.\d+)'
CALIB_PAT = '\s*(\S+)(?:[\s:,;]+)(%s(?:.*))+' % DECIMAL_PAT


class PolarizationDevice(device.Device):
    # For use in SI experiments, should be named "SI polarizer" in config.
    # TODO - identify the polarizer some other way.
    def __init__(self, name, config={}):
        device.Device.__init__(self, name, config)


    def readVoltagesFromConfig(self):
        # Re-read config files.
        config.read()
        # SI voltage map.
        if config.has_option(CONFIG_NAME, 'siVoltages'):
            for line in config.get(CONFIG_NAME, 'siVoltages').split('\n'):
                match = re.match(CALIB_PAT, line)
                if not match:
                    continue
                label = match.groups()[0].rstrip(':;,. ')
                values = re.findall(DECIMAL_PAT, match.groups()[1])
                try:
                    # Try to cast from str to int if label is a wavelength.
                    label = int(label)
                except:
                    pass
                if len(values) == 3:
                    self.voltages[label] = [float(v) for v in values]
                elif len(values) == 1:
                    self.voltages[label] = 3 * float(values[0])
                else:
                    raise Exception("%s: SI voltage spec. should be single value "
                                    "or one for each of the three angles." % str(label))

        if config.has_option(CONFIG_NAME, 'idleVoltage'):
            idleVoltage = config.get(CONFIG_NAME, 'idleVoltage')
        else:
            idleVoltage = 0.
        self.voltages[None] = 3 * [float(idleVoltage)]


    def initialize(self):
        ## Initialize device from config.
        # Analogue device module.
        lineDeviceName = config.get(CONFIG_NAME, 'lineDevice')
        executors = [d for d in depot.getHandlersInGroup('executor')
                      if d.name == lineDeviceName + ' experiment executor']
        if len(executors) == 0:
            raise Exception('No real executor for %s.' % CLASS_NAME)
        elif len(executors) > 1:
            raise Exception('Ambiguous executor for %s.' % CLASS_NAME)
        # Analogue line on device. Must be specified in config.
        if not config.has_option(CONFIG_NAME, 'line'):
            raise Exception('%s: No analogue line specified in config.' % CONFIG_NAME )
        line = config.get(CONFIG_NAME, 'line') or None
        # Analogue sensitivity. Default to 1 V/V.
        if config.has_option(CONFIG_NAME, 'sensitivity'):
            sens = config.get(CONFIG_NAME, 'sensitivity')
        else:
            sens = 1
        self.readVoltagesFromConfig()
        # Create the handler that drives the analogue line.
        self.lineHandler = executors[0].callbacks['registerAnalogue'](
                    'SI polarizer line', # axis
                    'structured illumination', # group
                    line, # physical line
                    self.voltages[None][0], # startup value
                    sens # sensitivity V/V
                    )


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
        self.executor = MyHandler(
                "SI polarizer",
                "structured illumination",
                True,
                {'examineActions': self.examineActions,
                    'getNumRunnableLines': self.getNumRunnableLines,
                    'executeTable': self.executeTable,
                    'moveAbsolute': self.moveAbsolute, 
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition, 
                    'getMovementTime': lambda: self.settlingTime,
                    'getLineHandler': lambda: self.lineHandler})

        #return (self.executor, self.mover)
        self.executor.deviceType = depot.EXECUTOR
        return (self.executor,)


    def getPosition(self):
        return self.curVoltage


    def moveAbsolute(self, pos):
        self.curVoltage = pos
        self.linehandler.moveAbsolute(pos)


    def moveRelative(self, delta):
        self.moveAbsolute(self.curVoltage + delta)


class MyHandler(handlers.analogueHandler.AnalogueHandlerMixin,
                handlers.executor.ExecutorHandler, 
                handlers.genericPositioner.GenericPositionerHandler):
    pass
