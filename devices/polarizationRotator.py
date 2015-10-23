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
import events
import handlers.analogueHandler, handlers.executor, handlers.genericPositioner
import util
from config import config

CLASS_NAME = 'PolarizationDevice'
CONFIG_NAME = 'polarizer'

class PolarizationDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        # Must have a lower priority than our analogue voltage source.
        self.priority = 1000
        if not self.isActive:
            return
        self.lineHandler = None
        # Movement time, settling time.
        self.timings = (decimal.Decimal(0.01), decimal.Decimal(0.01))
        self.voltages = {}
        self.curVoltage = 0.0


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
        # SI voltage map. Drop to defaults if missing.
        if config.has_option(CONFIG_NAME, 'siVoltages'):
            siVoltages = config.get(CONFIG_NAME, 'siVoltages')
        else:
            siVoltages = [1., 2., 3.]
        if config.has_option(CONFIG_NAME, 'idleVoltage'):
            idleVoltage = config.get(CONFIG_NAME, 'idleVoltage')
        else:
            idleVoltage = 0
        self.voltages = {n:siVoltages[n] for n in range(len(siVoltages))}
        self.voltages[None] = idleVoltage
        # Create the handler that drives the analogue line.
        self.lineHandler = executors[0].callbacks['registerAnalogue'](
                    'SI angle line', # axis
                    'structured illumination', # group
                    line, # physical line
                    self.voltages[None], # startup value
                    sens # sensitivity V/V
                    )


    def examineActions(self, name, table):
        ## Examine the action table.
        for i, (t, handler, action) in enumerate(table.actions):
            if handler is not self.executor:
                # Nothing to do
                continue
            # Action specifies an angle index.
            # Replace original event with analogue out event.
            table[i] = None
            table.clearBadEntries()
            table.addAction(t, self.lineHandler, self.voltages[action])


    def executeTable(self, name, table, startIndex, stopIndex, numReps,
            repDuration):
        for time, handler, action in table[startIndex:stopIndex]:
            if handler is self.executor:
                # Shouldn't have to do anything here.
                pass


    def getHandlers(self):      
        self.executor = MyHandler(
                "SI angle",
                "structured illumination",
                True,
                {'examineActions': self.examineActions,
                    'getNumRunnableLines': self.getNumRunnableLines,
                    'executeTable': self.executeTable,
                    'moveAbsolute': self.moveAbsolute, 
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition, 
                    'getMovementTime': lambda name, start, delta: self.timings,
                    'getLineHandler': lambda: self.lineHandler})

        #return (self.executor, self.mover)
        return (self.executor,)


    def getNumRunnableLines(self, name, table, curIndex):
        total = 0
        for time, handler, parameter in table[curIndex:]:
            if handler is not self.executor:
                return total
            total += 1
        

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