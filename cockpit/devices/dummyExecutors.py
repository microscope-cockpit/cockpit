#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.


from cockpit import depot
from . import device
from cockpit import events
import cockpit.handlers.executor

import time


class DummyExecutor(device.Device):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        self.deviceType = 'experiment executor'

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [cockpit.handlers.executor.ExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
                'executeTable': self.executeTable,})]

    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, table):
        pass

    ## Execute the table of experiment actions.
    def executeTable(self, name, table, startIndex, stopIndex, numReps,
            repDuration):
        # time this executor starts
        tStart = time.time()
        if startIndex > 0:
            tStart -= float(table[startIndex-1][0] / 1000)
        for i in range(numReps):
            for tTable, handler, action in table[startIndex:stopIndex]:
                tNext = float(tTable/1000) + tStart
                time.sleep(max(0, tNext - time.time()))
                if action and handler.deviceType == depot.CAMERA:
                    # Rising edge of a camera trigger: take an image.
                    events.publish("dummy take image", handler)
            if repDuration is not None:
                # Wait out the remaining rep time.
                # Convert repDuration from milliseconds to seconds.
                tWait = (repDuration / 1000) - (time.time() - tStart)
                time.sleep(max(0, tWait))
        events.publish("experiment execution")


class DummyDigitalExecutor(DummyExecutor):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        self.dlines = 0
        self.deviceType = depot.EXECUTOR

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [cockpit.handlers.executor.DigitalExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
             'executeTable': self.executeTable,
             'setDigital': self.setDigital,
             'readDigital': self.readDigital,
             'writeDigital': self.writeDigital},
            dlines=16)]

    def setDigital(self, line, state):
        print("Set d-line %s %s." % (line, ['low', 'high'][state]))
        if state:
            self.dlines |= 1<<line
        else:
            self.dlines -= self.state & 1<<line

    def readDigital(self):
        return self.dlines

    def writeDigital(self, state):
        self.dlines = state


    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, table):
        pass


class DummyAnalogDigitalExecutor(DummyDigitalExecutor):
    def __init__(self, name, config):
        device.Device.__init__(self, name, config)
        # Emulate for analogue lines.
        self.alines = [0]*4
        self.dlines = 0
        self.deviceType = depot.EXECUTOR

    ## Generate an ExperimentExecutor handler.
    def getHandlers(self):
        return [cockpit.handlers.executor.AnalogDigitalExecutorHandler(
            "Dummy experiment executor", "executor",
            {'examineActions': self.examineActions,
             'executeTable': self.executeTable,
             'setDigital': self.setDigital,
             'readDigital': self.readDigital,
             'writeDigital': self.writeDigital,
             'setAnalog': self.setAnalog,
             'getAnalog': self.getAnalog,},
            dlines=16, alines=len(self.alines))]

    def setAnalog(self, line, level):
        self.alines[line] = level
        print("Set a-line %s %s." % (line, level))

    def getAnalog(self, line):
        return self.alines[line]

    ## Given an experiment.ActionTable instance, examine the actions and
    # make any necessary modifications.
    def examineActions(self, table):
        pass

