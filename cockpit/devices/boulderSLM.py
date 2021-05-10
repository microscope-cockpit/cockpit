#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018-19 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
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

"""Boulder SLM."""

from collections import OrderedDict
import decimal
from cockpit.devices import device
from itertools import groupby
import Pyro4
import wx
import numpy as np

from cockpit import events
import cockpit.gui.device
import cockpit.gui.dialogs.getNumberDialog
import cockpit.handlers.executor
import time
import cockpit.util

class _LastParameters():
    """A class to keep a record of last SIM parmeters using async calls."""
    def __init__(self, slm):
        self.slm = slm
        self._params = None
        self._result = None
        from threading import Lock
        self._lock = Lock()

    @property
    def params(self):
        """Return the last recorded SIM parameters."""
        if self._result and self._result.ready:
            # Updated parameters are available.
            with self._lock:
                try:
                    self._params = self._result.value
                except:
                    pass
                finally:
                    self._result = None
        return self._params

    @params.setter
    def params(self, value):
        """Set recorded parameters explicitly."""
        with self._lock:
            self._result = None
            self._params = value

    def update(self):
        """Dispatch async call to update record from hardware."""
        if self.slm.asproxy:
            self._result = self.slm.asproxy.get_sim_sequence()

def generate_pattern_image(shape, dist, wavelength, NA, pixel_size):
    try:
        assert type(shape) is tuple
    except:
        raise Exception("Expected %s instead recieved %s" %(type((512,512)),type(shape)))

    try:
        assert len(shape) == 2
    except:
        raise Exception("Expected tuple of length 2, instead recieved length %i" % len(shape))

    ray_crit_dist = (1.22 * wavelength) / (2 * NA)
    ray_crit_freq = 1 / ray_crit_dist
    max_freq = 1 / (2 * pixel_size)
    freq_ratio = ray_crit_freq / max_freq
    OTF_outer_radx = freq_ratio * (shape[1] / 2)
    OTF_outer_rady = freq_ratio * (shape[0] / 2)

    pattern_ft = np.zeros(shape)

    f1x = shape[1]//2
    f1y = shape[0]//2
    f2x = f1x - int(np.round(0.5*OTF_outer_radx * dist))
    f2y = f1y - int(np.round(0.5 * OTF_outer_rady * dist))
    f3x = f1x + int(np.round(0.5*OTF_outer_radx * dist))
    f3y = f1y + int(np.round(0.5 * OTF_outer_rady * dist))
    f4x = f1x - int(np.round(OTF_outer_radx * dist))
    f4y = f1y - int(np.round(OTF_outer_rady * dist))
    f5x = f1x + int(np.round(OTF_outer_radx * dist))
    f5y = f1y + int(np.round(OTF_outer_rady * dist))
    freq_loc_half = (np.asarray([f2y, f2y, f3y, f3y], dtype="int64"),
                np.asarray([f2x, f3x, f2x, f3x], dtype="int64"))
    freq_loc_quart = (np.asarray([f1y, f1y, f4y, f5y], dtype="int64"),
                     np.asarray([f4x, f5x, f1x, f1x], dtype="int64"))
    pattern_ft[f1y,f1x] = 1
    pattern_ft[freq_loc_half] = 1/2
    pattern_ft[freq_loc_quart] = 1/4

    pattern_unscaled = abs(np.fft.fft2(np.fft.ifftshift(pattern_ft)))
    pattern = (pattern_unscaled/np.max(pattern_unscaled))*((2**16)-1)
    pattern = pattern.astype("uint16")
    return pattern

class BoulderSLM(device.Device):
    """Boulder SLM device.

    Sample config entry:

    .. code:: ini

        [slm]
        type: cockpit.devices.boulderSLM.BoulderSLM
        uri: PYRO:pyroSLM@slmhost:8000
        triggerSource: NAME_OF_EXECUTOR_DEVICE
        triggerLine: 2

    """

    _config_types = {
        'settlingtime': float,
        'triggerLine': int,
    }

    def __init__(self, name, config={}):
        super().__init__(name, config)
        self.connection = None
        self.asproxy = None
        self.position = None
        self.wasPowered = None
        self.slmTimeout = 10
        self.slmRetryLimit = 3
        self.last = _LastParameters(self)


    def initialize(self):
        if self.uri:
            uri = self.uri
        else:
            uri = "PYRO:pyroSLM@%s:%d" % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)
        self.asproxy = Pyro4.Proxy(uri)
        self.asproxy._pyroAsync()
        # If there's a diffraction angle in the config, set it on the remote.
        angle = self.config.get('diffractionangle', None)
        if angle:
            self.connection.set_sim_diffraction_angle(angle)

    def onExit(self) -> None:
        for proxy in [self.connection, self.asproxy]:
            if proxy is not None:
                proxy._pyroRelease()
        super().onExit()

    def finalizeInitialization(self):
        # A mapping of context-menu entries to functions.
        # Define in tuples - easier to read and reorder.
        menuTuples = (('Generate SIM sequence', self.testSIMSequence),
                      ('SIM diff. angle', self.setDiffractionAngle),
                      ('Apply IsoSense pattern', self.testIsoSensePattern),)
        # Store as ordered dict for easy item->func lookup.
        self.menuItems = OrderedDict(menuTuples)


    def getIsEnabled(self):
        return self.connection.get_is_enabled()


    def setEnabled(self, state):
        """Enable or disable the SLM."""
        if state:
            # Enable.
            if self.last.params == self.connection.get_sim_sequence():
                # Hardware and software sequences match
                targetPosition = self.getCurrentPosition()
            else:
                targetPosition = 0
            # Enable the hardware.
            self.connection.run()
            # Often, after calling connection.run(), the SLM pattern and the image
            # index reported are not synchronised until a few triggers have been
            # sent, so we need to compensate for this. We do the best we can,
            # but any other trigger-device activity during this call can mean that
            # we miss the target frame by +/- 1.
            for i in range(3):
                self.handler.triggerNow()
                time.sleep(0.01)
            # Cycle to the target position.
            self.cycleToPosition(targetPosition)
        else:
            # Disable the SLM.
            self.connection.stop()

    def cycleToPosition(self, targetPosition):
        pos = self.getCurrentPosition()
        delta = (targetPosition - pos) + (targetPosition < pos) * len(self.last.params)
        for i in range(delta):
            self.handler.triggerNow()
            time.sleep(0.01)

    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        # Found a table entry with a simple index. Trigger until that index
        # is reached.
        for t, h, args in table[startIndex:stopIndex]:
            events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                           'SLM moving to index %d' % args)
            self.cycleToPosition(args)

    def examineActions(self, table):
        # Extract pattern parameters from the table.
        # patternParms is a list of tuples (angle, phase, wavelength)
        patternParams = [row[2] for row in table if row[1] is self.handler]
        if not patternParams:
            # SLM is not used in this experiment.
            return

        # Remove consecutive duplicates and position resets.
        reducedParams = [p[0] for p in groupby(patternParams)
                          if type(p[0]) is tuple]
        # Find the repeating unit in the sequence.
        sequenceLength = len(reducedParams)
        for length in range(2, len(reducedParams) // 2):
            if reducedParams[0:length] == reducedParams[length:2*length]:
                sequenceLength = length
                break
        sequence = reducedParams[0:sequenceLength]
        ## Tell the SLM to prepare the pattern sequence.
        asyncResult = self.asproxy.set_sim_sequence(sequence)


        # Track sequence index set by last set of triggers.
        lastIndex = 0
        for i, (t, handler, action) in enumerate(table.actions):
            if handler is not self.handler:
                # Nothing to do
                continue
            # Action specifies a target frame in the sequence.
            # Remove original event.
            table[i] = None
            # How many triggers?
            if type(action) is tuple and action != sequence[lastIndex]:
                # Next pattern does not match last, so step one pattern.
                    numTriggers = 1
            elif type(action) is int:
                if action >= lastIndex:
                    numTriggers = action - lastIndex
                else:
                    numTriggers = sequenceLength - lastIndex - action
            else:
                numTriggers = 0
            """
            Used to calculate time to execute triggers and settle here, 
            then push back all later events, but that leads to very long
            delays before the experiment starts. For now, comment out
            this code, and rely on a fixed time passed back to the action
            table generator (i.e. experiment class).

            # How long will the triggers take?
            # Time between triggers must be > table.toggleTime.
            ## Shift later table entries to allow for triggers and settling.
            table.shiftActionsBack(time, dt)
            for trig in range(numTriggers):
                t = table.addToggle(t, triggerHandler)
                t += table.toggleTime
            """
            for trig in range(numTriggers):
                t = table.addToggle(t, self.handler)
                t += table.toggleTime

            lastIndex += numTriggers
            if lastIndex >= sequenceLength:
                lastIndex = lastIndex % sequenceLength
        table.clearBadEntries()
        # Wait until SLM has finished generating and loading patterns.
        self.wait(asyncResult, "SLM is generating pattern sequence.")
        # Store the parameters used to generate the sequence.
        self.last.params = sequence
        self.connection.run()
        # Fire several triggers to ensure that the sequence is loaded.
        for i in range(12):
            self.handler.triggerNow()
            time.sleep(0.01)
        # Ensure that we're at position 0.
        self.cycleToPosition(0)
        self.position = self.getCurrentPosition()


    def getCurrentPosition(self):
        return self.connection.get_sequence_index()


    def getHandlers(self):
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        dt = decimal.Decimal(self.config.get('settlingtime', 10))
        result = []
        self.handler = cockpit.handlers.executor.DelegateTrigger(
            "slm", "slm group", True,
            {'examineActions': self.examineActions,
             'getMovementTime': lambda *args: dt,
             'executeTable': self.executeTable,
             'setEnabled': self.setEnabled,
             'getIsEnabled': self.getIsEnabled})
        self.handler.delegateTo(trigsource, trigline, 0, dt)
        result.append(self.handler)
        return result


    ### UI functions ###
    def makeUI(self, parent):
        panel = wx.Panel(parent, style=wx.BORDER_RAISED)
        panel.SetDoubleBuffered(True)
        panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        powerButton = cockpit.gui.device.EnableButton(panel, self.handler)
        panel.Sizer.Add(powerButton, 0, wx.EXPAND)
        triggerButton = wx.Button(panel, label="step")
        triggerButton.Bind(wx.EVT_BUTTON, lambda evt: self.handler.triggerNow())
        panel.Sizer.Add(triggerButton, 0, wx.EXPAND)
        # Add a position display.
        posDisplay = cockpit.gui.device.MultilineDisplay(parent=panel, numLines=3)
        posDisplay.Bind(wx.EVT_TIMER,
                        lambda event: self.updatePositionDisplay(event))
        panel.Sizer.Add(posDisplay)
        # Set up a timer to update value displays.
        self.updateTimer = wx.Timer(posDisplay)
        self.updateTimer.Start(1000)
        # Changed my mind. SIM diffraction angle is an advanced parameter,
        # so it now lives in a right-click menu rather than on a button.
        panel.Bind(wx.EVT_CONTEXT_MENU, self.onRightMouse)
        # Controls other than powerButton only enabled when SLM is enabled.
        triggerButton.Disable()
        posDisplay.Disable()
        powerButton.manageStateOf((triggerButton, posDisplay))
        return panel


    def updatePositionDisplay(self, event):
        baseStr = 'angle:\t%s\nphase:\t%s\nwavel.:\t%s'
        # Get the display object. It seems there is variation between
        # wx versions. With some versions, the display is obtained by
        #    event.GetEventObject().
        # With others, it is
        #    event.GetEventObject().GetOwner()
        display = event.GetEventObject()
        if not hasattr(display, 'SetLabel'):
            display = display.GetOwner()
        self.position = self.getCurrentPosition()
        try:
            parms = self.last.params[self.position]
        except (IndexError, TypeError):
            # SLM parms updated since last position fetched, or lastParms is None.
            self.last.update()
            parms = None
        if parms:
            display.SetLabel(baseStr % parms)


    def onPrepareForExperiment(self, *args):
        self.position = self.getCurrentPosition()
        self.wasPowered = self.getIsEnabled()


    def cleanupAfterExperiment(self, *args):
        if not self.wasPowered:
            self.setEnabled(False)


    def performSubscriptions(self):
        #events.subscribe(events.USER_ABORT, self.onAbort)
        events.subscribe(events.PREPARE_FOR_EXPERIMENT, self.onPrepareForExperiment)
        events.subscribe(events.CLEANUP_AFTER_EXPERIMENT, self.cleanupAfterExperiment)


    def wait(self, asyncResult, message):
        # Wait unti the SLM has finished an aynchronous task.
        status = wx.ProgressDialog(parent = wx.GetApp().GetTopWindow(),
                title = "Waiting for SLM",
                message = message)
        status.Show()
        slmFailCount = 0
        slmFail = False
        while not asyncResult.wait(timeout=self.slmTimeout) and not slmFail:
            slmFailCount += 1
            if slmFailCount >= self.slmRetryLimit:
                slmFail = True
        status.Destroy()
        if slmFail:
            raise Exception('SLM timeout.')


    ### Context menu and handlers ###
    def menuCallback(self, index, item):
        func = self.menuItems[item]
        return func()


    def onRightMouse(self, event):
        menu = cockpit.gui.device.Menu(self.menuItems.keys(), self.menuCallback)
        menu.show(event)


    def testSIMSequence(self):
        inputs = cockpit.gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                None,
                'Generate a SIM sequence',
                ['wavelength',
                 'total angles',
                 'total phases',
                 'order\n0 for a then ph\n1 for ph then a'],
                 (488, 3, 5, 0))
        wavelength, angles, phases, order = [int(i) for i in inputs]
        if order == 0:
            params = [(theta, phi, wavelength)
                            for phi in range(phases)
                            for theta in range(angles)]
        elif order == 1:
            params = [(theta, phi, wavelength)
                            for theta in range(angles)
                            for phi in range(phases)]
        else:
            raise ValueError('Order must be 0 or 1.')
        ## Tell the SLM to prepare the pattern sequence.
        asyncResult = self.asproxy.set_sim_sequence(params)
        self.wait(asyncResult, "SLM is generating pattern sequence.")
        self.last.update()

    def testIsoSensePattern(self):
        inputs = cockpit.gui.dialogs.getNumberDialog.getManyNumbersFromUser(
            None,
            'Generate an IsoSense pattern',
            ['wavelength',
             'back pupil fill fraction'],
             (488, 50))
        wavelength, fill_frac = [float(i) for i in inputs]
        if fill_frac < 0 :
            raise ValueError("Fill fraction must be greater than 0")
        elif fill_frac > 100:
            raise ValueError("Fill fraction must be less than 100")
        else:
            pass
        ## Tell the SLM to prepare the pattern sequence.
        dist = fill_frac/100
        shape = self.connection.get_shape()
        pattern = generate_pattern_image(shape=shape, wavelength=wavelength*10**-9,
                                          dist=dist, NA=1.1, pixel_size=0.1193 * 10 ** -6)
        self.connection.set_custom_sequence(wavelength,[pattern,pattern])

    def setDiffractionAngle(self):
        try:
            theta = self.connection.get_sim_diffraction_angle()
        except:
            raise Exception('Could not communicate with SLM service.')
        newTheta = float(cockpit.gui.dialogs.getNumberDialog.getNumberFromUser(
                None,
                'Set SIM diffraction angle',
                ('Adjust diffraction angle to\nput spots at edge of pupil.\n'
                 u'Current angle is %.2f°.' % theta ),
                theta,
                atMouse=True))
        self.connection.set_sim_diffraction_angle(newTheta)