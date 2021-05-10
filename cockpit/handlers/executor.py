#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import typing

import matplotlib.pyplot as plt

import collections
from cockpit import depot
from cockpit.handlers.deviceHandler import DeviceHandler
from cockpit import events
from cockpit.handlers.genericPositioner import GenericPositionerHandler
from cockpit.experiment.actionTable import ActionTable
from cockpit.experiment import experiment
from numbers import Number
import operator
import time
from cockpit import util
import wx
import functools


## This handler is responsible for executing portions of experiments.
class ExecutorHandler(DeviceHandler):
    ## callbacks must include the following:
    # - examineActions(name, table): Perform any necessary validation or
    #   modification of the experiment's ActionTable.
    # - executeTable(name, table, startIndex, stopIndex): Actually perform
    #   actions through the specified lines in the ActionTable.
    def __init__(self, name, groupName, callbacks, dlines=None, alines=None):
        # \param name: handler name
        # \param groupname: handler and device group name
        # \param callbacks: callbacks, as above
        # \param dlines: optional, number of digital lines
        # \param alines: optional, number of analogue lines
        # Note that even though this device is directly involved in running
        # experiments, it is never itself a part of an experiment, so 
        # we pass False for isEligibleForExperiments here.
        super().__init__(name, groupName, False, callbacks, depot.EXECUTOR)
        # Base class contains empty dicts used by mixins so that methods like
        # getNumRunnableLines can be implemented here for all mixin combos. This
        # works just great, but is probably a horrible abuse of OOP. It might be
        # cleaner to have a single list of clients.
        self.digitalClients = {}
        self.analogClients = {}
        # Number of digital and analogue lines.
        self._dlines = dlines
        self._alines = alines
        if not isinstance(self, DigitalMixin):
            self.registerDigital = self._raiseNoDigitalException
            self.getDigital = self._raiseNoDigitalException
            self.setDigital = self._raiseNoDigitalException
            self.readDigital = self._raiseNoDigitalException
            self.writeDigital = self._raiseNoDigitalException
            self.triggerDigital = self._raiseNoDigitalException
        if not isinstance(self, AnalogMixin):
            self.registerAnalog = self._raiseNoAnalogException
            self.setAnalog = self._raiseNoAnalogException
            self.getAnalog = self._raiseNoAnalogException
            self.setAnalogClient = self._raiseNoAnalogException
            self.getAnalogClient = self._raiseNoAnalogException
        events.subscribe(events.PREPARE_FOR_EXPERIMENT, self.onPrepareForExperiment)
        events.subscribe(events.CLEANUP_AFTER_EXPERIMENT, self.cleanupAfterExperiment)

    def examineActions(self, table):
        return self.callbacks['examineActions'](table)

    def getNumRunnableLines(self, table, index):
        ## Return number of lines this handler can run.
        count = 0
        for time, handler, parameter in table[index:]:
            # Check for analog and digital devices we control.
            if (handler is not self and
                   handler not in self.digitalClients and
                   handler not in self.analogClients):
                # Found a device we don't control.
                break
            count += 1
        return count

    def _raiseNoDigitalException(self, *args, **kwargs):
        raise Exception("Digital lines not supported.")

    def _raiseNoAnalogException(self, *args, **kwargs):
        raise Exception("Analog lines not supported.")

    ## Run a portion of a table describing the actions to perform in a given
    # experiment.
    # \param table An ActionTable instance.
    # \param startIndex Index of the first entry in the table to run.
    # \param stopIndex Index of the entry before which we stop (i.e. it is
    #        not performed).
    # \param numReps Number of times to iterate the execution.
    # \param repDuration Amount of time to wait between reps, or None for no
    #        wait time. 
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        # The actions between startIndex and stopIndex may include actions for
        # this handler, or for this handler's clients. All actions are
        # ultimately carried out by this handler, so we need to parse the
        # table to replace client actions, resulting in a table of
        # (time, (analogStage, digitalState)).
        if isinstance(self, DigitalMixin):
            dstate = self.readDigital()
        else:
            dstate = None
        if isinstance(self, AnalogMixin):
            astate = [self.getAnalogLine(line) for line in range(self._alines)]
        else:
            astate = None

        actions = []

        tPrev = None
        hPrev = None
        argsPrev = None

        for i in range(startIndex, stopIndex):
            t, h, args = table[i]
            if h in self.analogClients:
                # update analog state
                lineHandler = self.analogClients[h]
                if isinstance(args, collections.Iterable):
                    # Using an indexed position
                    pos = lineHandler.indexedPosition(*args)
                else:
                    pos = args
                astate[lineHandler.line] = lineHandler.posToNative(pos)
            elif h in self.digitalClients:
                # set/clear appropriate bit
                change = 1 << self.digitalClients[h]
                # args contains new bit state
                if args:
                    dstate |= change
                else:
                    dstate = dstate & (2**self._dlines - 1) - (change)

            # Check for simultaneous actions.
            if tPrev is not None and t == tPrev:
                if h not in hPrev:
                    # Update last action to merge actions at same timepoint.
                    actions[-1] = (t, (dstate, astate[:]))
                    # Add handler and args to list for next check.
                    hPrev.append(h)
                    argsPrev.append(args)
                elif args == argsPrev[hPrev.index(h)]:
                    # Just a duplicate entry
                    continue
                else:
                    # Simultaneous, different actions with same handler.
                    raise Exception("Simultaneous actions with same hander, %s." % h)
            else:
                # Append new action.
                actions.append((t, (dstate, astate[:])))
                # Reinitialise hPrev and argsPrev for next check.
                hPrev, argsPrev = [h], [args]
                tPrev = t

        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                       'Waiting for %s to finish' % self.name)

        return self.callbacks['executeTable'](actions, 0, len(actions), numReps,
                                              repDuration)

    ## Debugging function: display ExecutorOutputWindow.
    def showDebugWindow(self):
        # Ensure only a single instance of the window.
        global _windowInstance
        window = globals().get('_windowInstance')
        if window:
            try:
                window.Raise()
                return None
            except:
                pass
        # If we get this far, we need to create a new window.
        _windowInstance = ExecutorDebugWindow(self, parent=wx.GetApp().GetTopWindow())
        _windowInstance.Show()

    def onPrepareForExperiment(self, experiment):
        # This smells sketchy, but does exactly what we need: run
        # the method on all mixins contributing to a hybrid class.
        # Could do achieve the same by having mixins append to a list
        # of actions to call on certain events.
        for c in self.__class__.__mro__[1:]:
            if hasattr(c, '_onPrepareForExperiment'):
                c._onPrepareForExperiment(self)

    def cleanupAfterExperiment(self, isCleanupFinal=True):
        # See comments in onPrepareForExperiment
        for c in self.__class__.__mro__[1:]:
            if hasattr(c, '_cleanupAfterExperiment'):
                c._cleanupAfterExperiment(self, isCleanupFinal)



class DigitalMixin:
    ## Digital handler mixin.

    ## Register a client device that is connected to one of our lines.
    # returns a virtual TriggerProxy.
    def registerDigital(self, client, line):
        h = TriggerProxy(client.name, self)
        self.digitalClients[h] = int(line)
        # If the client not a DelegateTrigger executor, all of its actions
        # are handled here.
        if not isinstance(client, DelegateTrigger):
            self.digitalClients[client] = int(line)
        return h


    ## Set or clear a single line.
    def setDigital(self, line, state):
        if line is None:
            return
        line = int(line)
        if self.callbacks.get('setDigital', None):
            self.callbacks['setDigital'](line, state)
        else:
            oldstate = self.readDigital()
            if state:
                newstate = oldstate | 1<<line
            else:
                newstate = oldstate & (2**self._dlines - 1) - (1<<line)
            self.writeDigital(newstate)

    def writeDigital(self, state):
        self.callbacks['writeDigital'](state)

    def readDigital(self):
        return self.callbacks['readDigital']()

    def triggerDigital(self, client, dt=0.01):
        ## Trigger a client line now.
        line = self.digitalClients.get(client, None)
        if line:
            self.setDigital(line, True)
            time.sleep(dt)
            self.setDigital(line, False)

    @property
    def activeLights(self):
        return list(filter(lambda h: h.deviceType==depot.LIGHT_TOGGLE
                                and h.getIsEnabled(),
                      self.digitalClients))

    @property
    def activeCameras(self):
        return list(filter(lambda h: h.deviceType == depot.CAMERA
                                and h.getIsEnabled(),
                      self.digitalClients))

    def takeImage(self):
        if not self.digitalClients:
            # No triggered devices registered.
            return
        camlines = sum([1<<self.digitalClients[cam] for cam in self.activeCameras])

        if camlines == 0:
            # No cameras to be triggered.
            return

        ltpairs = []
        for light in self.activeLights:
            lline = 1 << self.digitalClients[light]
            ltime = light.getExposureTime()
            ltpairs.append((lline, ltime))

        # Sort by exposure time
        ltpairs.sort(key = lambda item: item[1])

        # Generate a sequence of (time, digital state)
        # TODO: currently uses bulb exposure; should support other modes.
        if ltpairs:
            # Start by all active cameras and lights.
            state = camlines | functools.reduce(operator.ior, list(zip(*ltpairs))[0])
            seq = [(0, state)]
            # Switch off each light as its exposure time expires.
            for  lline, ltime in ltpairs:
                state -= lline
                seq.append( (ltime, state))
        else:
            # No lights. Just trigger the cameras.
            seq = [(0, camlines)]

        # If there is an ambient light enabled, extend exposure as
        # necessary (see issue #669).
        ambient = depot.getHandlerWithName('Ambient')
        if ambient is not None and ambient.getIsEnabled():
            t = ambient.getExposureTime()
            if t > seq[-1][0]:
                seq.append((ambient.getExposureTime(), 0))

        # Switch all lights and cameras off.
        seq.append( (seq[-1][0] + 1, 0) )
        if self.callbacks.get('runSequence', None):
            self.callbacks['runSequence'](seq)
        else:
            self.softSequence(seq)

    def writeWithMask(self, mask, state):
        initial = self.readDigital()
        final = (initial & ~mask) | state
        self.writeDigital( final )

    @util.threads.callInNewThread
    def softSequence(self, seq):
        # Mask of the bits that we toggle
        mask = functools.reduce(operator.ior, list(zip(*seq))[1])
        entryState = self.readDigital()
        t_last = 0
        for t, state in seq:
            if t != t_last:
                time.sleep( (t - t_last) / 1000.)
                t_last = t
            self.writeWithMask(mask, state)
        self.writeDigital(entryState)


class AnalogMixin:
    ## Analog handler mixin.
    # Consider output 'level' in volts, amps or ADUS, and input
    # 'position' in experimental units (e.g. um or deg).
    # level = gain * (offset + position)
    # gain is in units of volts, amps or ADUS per experimental unit.
    # offset is in experimental units.

    def registerAnalog(self, client, line, offset=0, gain=1, movementTimeFunc=None):
        ## Register a client device that is connected to one of our lines.
        # Returns an AnalogLineHandler for that line.
        h = AnalogLineHandler(client.name, self.name + ' analogs',
                              self, int(line), offset, gain, movementTimeFunc)
        # May reference the client by whatever we were passed or its new handler
        self.analogClients[client] = h
        self.analogClients[h] = h
        return h

    def setAnalogLine(self, line, level):
        ## Set analog output of line to level.
        self.callbacks['setAnalog'](line, level)

    def getAnalogLine(self, line):
        ## Get level of analog line.
        return self.callbacks['getAnalog'](line)

    def _onPrepareForExperiment(self):
        for client in self.analogClients:
            self.analogClients[client].savePosition()

    def _cleanupAfterExperiment(self, isCleanupFinal=True):
        if isCleanupFinal:
            for client in self.analogClients:
                self.analogClients[client].restorePosition()



class AnalogLineHandler(GenericPositionerHandler):
    ## A type of GenericPositioner for analog outputs.
    # Handles absolute and indexed positions in action table.
    #   absolute:   time, handler, float or int
    #   indexed:    time, handler, (index, wavelength or None or 'default')
    def __init__(self, name, groupName, asource, line, offset, gain, movementTimeFunc):
        # Indexed positions. Can be a dict if wavelength-independent, or
        # a mapping of wavelengths (as floats or ints) to lists of same length.
        self.positions = []
        # Scaling parameters
        self.gain = gain
        self.offset = offset
        # Line, required when executing table.
        self.line = line
        # Saved position
        self._savedPos = None
        # Set up callbacks used by GenericPositionHandler methods.
        self.callbacks = {}
        self.callbacks['moveAbsolute'] = lambda pos: asource.setAnalogLine(line, self.posToNative(pos))
        self.callbacks['getPosition'] = lambda: self.nativeToPos(asource.getAnalogLine(line))
        ## TODO - consider if we want to fallback to number or zero, or raise an exception here.
        if callable(movementTimeFunc):
            self.callbacks['getMovementTime'] = movementTimeFunc
        elif isinstance(movementTimeFunc, Number):
            self.callbacks['getMovementTime'] = lambda *args: (movementTimeFunc, 0)
        else:
            self.callbacks['getMovementTime'] = lambda *args: (0, 0)
        super().__init__(name, groupName, True, self.callbacks)

    def savePosition(self):
        self._savedPos = self.getPosition()

    def restorePosition(self):
        self.moveAbsolute(self._savedPos)

    def moveRelative(self, delta):
        self.callbacks['moveAbsolute'](self.callbacks['getPosition']() + delta)

    def posToNative(self, pos):
        return self.gain * (self.offset + pos)

    def nativeToPos(self, native):
        return (native / self.gain) - self.offset

    def indexedPosition(self, index, wavelength=None):
        pos = None
        if isinstance(wavelength, Number)  and isinstance(self.positions, dict):
            wls = [int(wl) for wl in self.positions if wl and
                   isinstance(int(wl), Number)]
            wl = min(wls, key=lambda w: abs(w - wavelength))
            ps = self.positions[str(wl)]
        elif isinstance(self.positions, dict):
            if None in self.positions:
                ps = self.positions[None]
            elif 'default' in self.positions:
                ps = self.positions['default']
            else:
                raise Exception('No wavelength specified, and no default in indexed positions.')
        else:
            ps = self.positions
        return ps[index]


class DigitalExecutorHandler(DigitalMixin, ExecutorHandler):
    pass


class AnalogExecutorHandler(AnalogMixin, ExecutorHandler):
    pass


class AnalogDigitalExecutorHandler(AnalogMixin, DigitalMixin, ExecutorHandler):
    pass


def plot_action_table_profile(
    action_table: ActionTable,
    handlers: typing.Optional[typing.List[DeviceHandler]] = None,
) -> None:
    """Plot the timing profile of an action table like an oscilloscope display.

    Args:
        action_table: the action table to plot.
        handlers: if not None, only plot actions for the given
            handlers.
    """
    # We first construct a more usable table
    table = {}

    def action_type(action):
        if isinstance(action, bool):
            return "digital"
        if isinstance(action, (float, int)):
            return "analogue"

    for event in action_table.actions:
        if event is None:
            continue
        time, handler, action = event
        if handlers is None or handler in handlers:
            if handler.name in table:
                # The handler already exists in the table
                if (table[handler.name][2] == 'digital'):
                    #if digital have a point with last state at this time.
                    table[handler.name][0].append(time)
                    table[handler.name][1].append(table[handler.name][1][-1])
                table[handler.name][0].append(time)
                table[handler.name][1].append(action)
            else:
                table[handler.name] = ([time], [action], action_type(action))

    # Generate the actual plot
    fig, axs = plt.subplots(len(table), 1, sharex=True)
    fig.subplots_adjust(hspace=0)  # Remove horizontal space between axes
    for i, (key, data) in enumerate(table.items()):
        if data[2] == "analogue":
            axs[i].plot(data[0], data[1])
        else:
            axs[i].step(data[0], data[1], where="post")
            axs[i].set_yticks([0, 1])
            axs[i].set_ylim(-0.1, 1.1)
        axs[i].set_xlabel("Time", fontsize=12)
        axs[i].set_ylabel(key, fontsize=12)
        axs[i].grid(True, which="both", axis="x")

    plt.show(block=False)


## This debugging window allows manipulation of analogue and digital lines.
class ExecutorDebugWindow(wx.Frame):
    def __init__(self, handler, parent, *args, **kwargs):
        title = handler.name + " Executor control lines"
        kwargs['style'] = wx.SYSTEM_MENU | wx.CAPTION | wx.CLOSE_BOX | wx.CLIP_CHILDREN
        super().__init__(parent, title=title, *args, **kwargs)
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        if handler._dlines is not None:
            # Digital controls
            ncols = 8
            nrows = (handler._dlines + ncols - 1) // ncols
            buttonSizer = wx.GridSizer(nrows, ncols, 1, 1)
            for line in range(handler._dlines):
                clients = [k.name for k,v in handler.digitalClients.items() if v==line]
                if clients:
                    label = '\n'.join(clients)
                else:
                    label = str(line)
                button = wx.ToggleButton(panel, wx.ID_ANY, label)
                button.Bind(wx.EVT_TOGGLEBUTTON,
                            lambda evt, line=line: handler.setDigital(line, evt.EventObject.Value))
                buttonSizer.Add(button, 1, wx.EXPAND)
            mainSizer.Add(buttonSizer)

            # Analog controls
            # These controls deal with hardware units, i.e. probably ADUs.
            anaSizer = wx.BoxSizer(wx.HORIZONTAL)
            for line in range(handler._alines):
                anaSizer.Add(wx.StaticText(panel, -1, "output %d:" % line))
                control = wx.TextCtrl(panel, -1, size=(60, -1),
                                      style=wx.TE_PROCESS_ENTER)
                control.Bind(wx.EVT_TEXT_ENTER,
                             lambda evt, line=line, ctrl=control:
                                handler.setAnalogLine(line, float(ctrl.GetValue()) ))
                                # If dealing with ADUs, float should perhaps be int,
                                # but rely on device to set correct type.
                anaSizer.Add(control, 0, wx.RIGHT, 20)

            btn = wx.Button(panel, label="Display last experiment")
            btn.SetToolTip(wx.ToolTip(
                "Plot the last experiment like an oscilloscope display."
            ))
            btn.Bind(wx.EVT_BUTTON, self._OnDisplayLastExperiment)
            anaSizer.Add(btn, 0, wx.RIGHT, 20)
            mainSizer.Add(anaSizer)

        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())

    def _OnDisplayLastExperiment(self, evt: wx.CommandEvent) -> None:
        del evt
        if experiment.lastExperiment is None:
            wx.MessageBox("No experiment has been done yet.")
        else:
            plot_action_table_profile(experiment.lastExperiment.table)


## A class for a handler that can perform actions in an experiment,
# but doesn't have any analogue or digital capabilities.
class SimpleExecutor(DeviceHandler):
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        super().__init__(name, groupName, isEligibleForExperiments,
                         callbacks, depot.EXECUTOR)
        for cbname, cb in callbacks.items():
            if cbname == 'executeTable':
                continue
            if not callable(cb):
                cb = lambda *args, **kwargs: cb
            self.__setattr__(cbname, cb)

    ## Execute whatever the device does and publish an event on completion.
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        self.callbacks['executeTable'](table, startIndex, stopIndex,
                                       numReps, repDuration)
        events.publish(events.EXPERIMENT_EXECUTION)


    ## Return number of lines this handler can run.
    def getNumRunnableLines(self, table, index):
        count = 0
        if not self.isEligibleForExperiments:
            return 0
        for time, handler, parameter in table[index:]:
            if handler is not self:
                break
            count += 1
        return count


## A trigger handler to allow discrimination of trigger and
# triggered device in the action table.
class TriggerProxy(DeviceHandler):
    def __init__(self, name, trigSource):
        super().__init__(name + " trigger", name + " group",
                         False, {}, depot.GENERIC_DEVICE)
        self.triggerNow = lambda: trigSource.triggerDigital(self)


## This handler can examine and modify an action table, but delegates
# running it to some other ExecutorHandler.
# The DelegateTrigger instance should be created with any non-trigger actions
# handled in callback named 'executeTable', and then connected to a trigger
# source with the delegateTo method.

class DelegateTrigger(SimpleExecutor):
    #def __init__(self, name, groupName, trigSource, trigLine, examineActions, movementTime=0):
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        super().__init__(name, groupName, isEligibleForExperiments, callbacks)
        self._trigger = None
        self._triggerTime = 0
        self._responseTime = 0
        self.triggerNow = lambda: None


    ## Delegate trigger actions to some trigSource
    def delegateTo(self, trigSource, trigLine, trigTime=0, responseTime=0):
        if isinstance(trigSource, str):
            trigSource = depot.getHandler(trigSource, depot.EXECUTOR)
        self._trigger = trigSource.registerDigital(self, trigLine)
        self.triggerNow = self._trigger.triggerNow
        self._triggerTime = trigTime
        self._responseTime = responseTime


    ## Add a toggle event to the action table.
    # Return time of last action, and response time before ready after trigger.
    def addToggle(self, time, table):
        dt = max(self._triggerTime, table.toggleTime)
        table.addAction(time, self._trigger, True)
        table.addAction(time + dt, self._trigger, False)
        return time + dt, self._responseTime
