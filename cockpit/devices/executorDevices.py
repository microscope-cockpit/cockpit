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

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


## This module handles interacting with the DSP card that sends the digital and
# analog signals that control our light sources, cameras, and piezos. In 
# particular, it effectively is solely responsible for running our experiments.
# As such it's a fairly complex module. 
# 
# A few helpful features that need to be accessed from the commandline:
# 1) A window that lets you directly control the digital and analog outputs
#    of the DSP.
# >>> import devices.dsp as DSP
# >>> DSP.makeOutputWindow()
#
# 2) Create a plot describing the actions that the DSP set up in the most
#    recent experiment profile.
# >>> import devices.dsp as DSP
# >>> DSP._deviceInstance.plotProfile()
#
# 3) Manually advance the SLM forwards some number of steps; useful for when
#    it has gotten offset and is no longer "resting" on the first pattern.
# >>> import devices.dsp as DSP
# >>> DSP._deviceInstance.advanceSLM(numSteps)
# (where numSteps is an integer, the number of times to advance it).
#
# Sample config entry:
#  [dsp]
#  type: LegacyDSP
#  uri: PYRO:pyroDSP@somehost:8001


import Pyro4
import time

from cockpit import depot
from cockpit.devices import device
from cockpit import events
import cockpit.handlers.executor
import cockpit.handlers.imager
import cockpit.util.threads
import numpy as np
from itertools import chain


class ExecutorDevice(device.Device):
    _config_types = {
        'alines' : int,
        'dlines' : int,
    }

    def __init__(self, name, config={}):
        super().__init__(name, config)
        ## Connection to the remote DSP computer
        self.connection = None
        ## Set of all handlers we control.
        self.handlers = set()

    ## Connect to the DSP computer.
    @cockpit.util.threads.locked
    def initialize(self):
        self.connection = Pyro4.Proxy(self.uri)
        self.connection._pyroTimeout = 6
        self.connection.Abort()

    def onExit(self) -> None:
        if self.connection is not None:
            self.connection._pyroRelease()
        super().onExit()

    # Subscribe to events.
    def performSubscriptions(self):
        events.subscribe(events.USER_ABORT, self.onAbort)
        events.subscribe(events.PREPARE_FOR_EXPERIMENT, self.onPrepareForExperiment)

    ## As a side-effect of setting our initial positions, we will also
    # publish them. We want the Z piezo to be in the middle of its range
    # of motion.
    def makeInitialPublications(self):
        pass

    ## User clicked the abort button.
    def onAbort(self):
        self.connection.Abort()
        # Various threads could be waiting for a 'DSP done' event, preventing
        # new DSP actions from starting after an abort.
        events.publish(events.EXECUTOR_DONE % self.name)


    @cockpit.util.threads.locked
    def finalizeInitialization(self):
        # Tell the remote DSP computer how to talk to us.
        server = depot.getHandlersOfType(depot.SERVER)[0]
        self.receiveUri = server.register(self.receiveData)
        self.connection.receiveClient(self.receiveUri)


    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        h = cockpit.handlers.executor.AnalogDigitalExecutorHandler(
            self.name, "executor",
            {'examineActions': lambda *args: None,
             'executeTable': self.executeTable,
             'readDigital': self.connection.ReadDigital,
             'writeDigital': self.connection.WriteDigital,
             'getAnalog': self.connection.ReadPosition,
             'setAnalog': self.connection.MoveAbsolute,
             },
            dlines=self.config.get('dlines', 16),
            alines=self.config.get('alines', 4))

        result.append(h)

        # The takeImage behaviour is now on the handler. It might be better to
        # have hybrid handlers with multiple inheritance, but that would need
        # an overhaul of how depot determines handler types.
        result.append(cockpit.handlers.imager.ImagerHandler(
            "%s imager" % (self.name), "imager",
            {'takeImage': h.takeImage}))

        self.handlers = set(result)
        return result


    ## Receive data from the executor remote.
    def receiveData(self, action, *args):
        if action.lower() in ['done', 'dsp done']:
            events.publish(events.EXECUTOR_DONE % self.name)


    def triggerNow(self, line, dt=0.01):
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)
        time.sleep(dt)
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)


    ## Prepare to run an experiment.
    def onPrepareForExperiment(self, *args):
        # Ensure remote has the correct URI set for sending data/notifications.
        self.connection.receiveClient(self.receiveUri)


    ## Actually execute the events in an experiment ActionTable, starting at
    # startIndex and proceeding up to but not through stopIndex.
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):

        actions = actions_from_table(table, startIndex, stopIndex, repDuration)

        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                       'Waiting for DSP to finish')
        self.connection.PrepareActions(actions, numReps)
        events.executeAndWaitFor(events.EXECUTOR_DONE % self.name, self.connection.RunActions)
        events.publish(events.EXPERIMENT_EXECUTION)
        return


        ## Debugging function: set the digital output for the DSP.
    def setDigital(self, value):
        self.connection.WriteDigital(value)


class LegacyDSP(ExecutorDevice):
    #        May need to wrap profile digitals and analogs in numpy object.
    def __init__(self, name, config):
        super().__init__(name, config)
        self.tickrate = 10 # Number of ticks per ms.
        # We store the current position for each analogue channel, because
        # reasons:
        # - analogue readback functions on the remote are not reliable, as
        #   they use arbitrary scaling that varies from device to device,
        #   often from channel to channel, bears no resemblance to the voltage
        #   produced, and has no clear way to be queried or set;
        # - movement 'profiles' on the DSP use ADU offsets from a start position,
        #   so it is convenient to use ADU as the native unit for this device;
        #   the remote offers a function to set an absolute position in ADUs, but
        #   there is not a direct, transparent or documented way to read back in
        #   ADUs.
        self._currentAnalogs = 4*[0]
        # Absolute positions prior to the start of the experiment.
        self._lastAnalogs = 4*[0]
        # Store last movement profile for debugging
        self._lastProfile = None

    def finalizeInitialization(self):
        super().finalizeInitialization()
        for line in range(4):
            self.setAnalog(line, 65536//2)

    def onPrepareForExperiment(self, *args):
        super().onPrepareForExperiment(*args)
        self._lastAnalogs = [line for line in self._currentAnalogs]
        self._lastDigital = self.connection.ReadDigital()


    ## Receive data from the DSP computer.
    def receiveData(self, action, *args):
        if action.lower() == 'dsp done':
            events.publish(events.EXECUTOR_DONE % self.name)

    ## Return analog position in native units
    def getAnalog(self, line):
        return self._currentAnalogs[line]

    ## Set analog position in native units
    def setAnalog(self, line, target):
        self._currentAnalogs[line] = target
        return self.connection.MoveAbsoluteADU(line, int(target))

    ## We control which light sources are active, as well as a set of
    # stage motion piezos.
    def getHandlers(self):
        result = []
        h = cockpit.handlers.executor.AnalogDigitalExecutorHandler(
            self.name, "executor",
            {'examineActions': lambda *args: None,
             'executeTable': self.executeTable,
             'readDigital': self.connection.ReadDigital,
             'writeDigital': self.connection.WriteDigital,
             'getAnalog': self.getAnalog,
             'setAnalog': self.setAnalog,
             },
            dlines=16, alines=4)

        result.append(h)

        # The takeImage behaviour is now on the handler. It might be better to
        # have hybrid handlers with multiple inheritance, but that would need
        # an overhaul of how depot determines handler types.
        result.append(cockpit.handlers.imager.ImagerHandler(
            "%s imager" % (self.name), "imager",
            {'takeImage': h.takeImage}))

        self.handlers = set(result)
        return result


    ## Actually execute the events in an experiment ActionTable, starting at
    # startIndex and proceeding up to but not through stopIndex.
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        # Take time and arguments (i.e. omit handler) from table to generate actions.
        # For the UCSF m6x DSP device, we also need to:
        #  - make the analogue values offsets from the current position;
        #  - convert float in ms to integer clock ticks and ensure digital
        #    lines are not changed twice on the same tick;
        #  - separate analogue and digital events into different lists;
        #  - generate a structure that describes the profile.

        actions = actions_from_table(table, startIndex, stopIndex, repDuration)

        # Profiles
        analogs = [ [], [], [], [] ] # A list of lists (one per channel) of tuples (ticks, (analog values))
        digitals = [] # A list of tuples (ticks, digital state)
        # Need to track time of last analog events to workaround a
        # DSP bug later. Also used to detect when events exceed timing
        # resolution
        tLastA = None


        # The DSP executes an analogue movement profile, which is defined using
        # offsets relative to a baseline at the time the profile was initialized.
        # These offsets are encoded as unsigned integers, so at profile
        # intialization, each analogue channel must be at or below the lowest
        # value it needs to reach in the profile.
        lowestAnalogs = list(np.amin([x[1][1] for x in actions], axis=0))
        for line, lowest in enumerate(lowestAnalogs):
            if lowest < self._lastAnalogs[line]:
                self._lastAnalogs[line] = lowest
                self.setAnalog(line, lowest)

        for (t, (darg, aargs)) in actions:
            # Convert t to ticks as int while rounding up. The rounding is
            # necessary, otherwise e.g. 10.1 and 10.1999999... both result in 101.
            ticks = int(float(t) * self.tickrate + 0.5)

            # Digital actions - one at every time point.
            if len(digitals) == 0:
                digitals.append((ticks, darg))
            elif ticks == digitals[-1][0]:
                # Used to check for conflicts here, but that's not so trivial.
                # We need to allow several bits to change at the same time point, but
                # they may show up as multiple events in the actionTable. For now, just
                # take the most recent state.
                if darg != digitals[-1][1]:
                    digitals[-1] = (ticks, darg)
                else:
                    pass
            else:
                digitals.append((ticks, darg))

            # Analogue actions - only enter into profile on change.
            # DSP uses offsets from value when the profile was loaded.
            offsets = map(lambda base, new: new - base, self._lastAnalogs, aargs)
            for offset, a in zip(offsets, analogs):
                if ( (len(a) == 0 ) or (len(a) > 0 and offset != a[-1][1])):
                    a.append((ticks, offset))
                    tLastA = t

        # Work around some DSP bugs:
        # * The action table needs at least two events to execute correctly.
        # * Last action must be digital --- if the last analog action is at the same
        #   time or after the last digital action, it will not be performed.
        # Both can be avoided by adding a digital action that does nothing.
        if len(digitals) == 1 or tLastA >= digitals[-1][0]:
            # Just duplicate the last digital action, one tick later.
            digitals.append( (digitals[-1][0]+1, digitals[-1][1]) )

        # Update records of last positions.
        self._lastDigital = digitals[-1][1]
        self._lastAnalogs = list(map(lambda x, y: x - (y[-1:][1:] or 0), self._lastAnalogs, analogs))

        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                       'Waiting for DSP to finish')
        # Convert digitals to array of uints.
        digitalsArr = np.array(digitals, dtype=np.uint32).reshape(-1,2)
        # Convert analogs to array of uints.
        analogsArr = [np.array(a, dtype=np.uint32).reshape(-1, 2) for a in analogs]


        # Create a description dict. Will be byte-packed by server-side code.
        maxticks = max(chain([d[0] for d in digitals],
                             [a[0] for a in chain.from_iterable(analogs)]))
        description = {}
        description['count'] = maxticks
        description['clock'] = 1000. / float(self.tickrate)
        description['InitDio'] = self._lastDigital
        description['nDigital'] = len(digitals)
        description['nAnalog'] = [len(a) for a in analogs]

        self._lastProfile = (description, digitalsArr, analogsArr)

        self.connection.profileSet(description, digitalsArr, *analogsArr)
        self.connection.DownloadProfile()
        self.connection.InitProfile(numReps)
        events.executeAndWaitFor(events.EXECUTOR_DONE % self.name, self.connection.trigCollect)
        events.publish(events.EXPERIMENT_EXECUTION)


def actions_from_table(table, startIndex, stopIndex, repDuration):
    ## Take time and arguments (i.e. omit handler) from table to
    ## generate actions.
    t0 = float(table[startIndex][0])
    actions = [(float(row[0])-t0,) + tuple(row[1:])
               for row in table[startIndex:stopIndex]]

    ## If there are repeats, add an extra action to wait until
    ## repDuration expired.
    if repDuration is not None:
        repDuration = float(repDuration)
        if actions[-1][0] < repDuration:
            ## Repeat the last event at t0 + repDuration
            actions.append((t0+repDuration,) + tuple(actions[-1][1:]))
    return actions
