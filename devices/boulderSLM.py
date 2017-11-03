#!/usr/bin/python
# -*- coding: UTF8   -*-
""" This module makes a BNS SLM  device available to Cockpit.

Mick Phillips, University of Oxford, 2014-2015.
"""

from collections import OrderedDict
import decimal
import depot
import device
from itertools import groupby
import Pyro4
import wx

import events
import gui.device
import gui.guiUtils
import gui.toggleButton
import handlers
import time
import util
from config import config
from experiment import actionTable

CLASS_NAME = 'BoulderSLMDevice'
CONFIG_NAME = 'slm'

class BoulderSLMDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        # Must have a lower priority than our trigger source.
        self.priority = 1000
        if not self.isActive:
            return

        self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
        self.port = int(config.get(CONFIG_NAME, 'port'))
        self.connection = None
        self.async = None
        self.executor = None
        self.order = None
        self.position = None
        self.wasPowered = None
        self.settlingTime = decimal.Decimal('10.0')
        self.slmTimeout = int(config.get(CONFIG_NAME, 'timeout', default=10))
        self.slmRetryLimit = int(config.get(CONFIG_NAME, 'retryLimit', default=3))
        self.lastParms = None
        # A mapping of context-menu entries to functions.
        # Define in tuples - easier to read and reorder.
        menuTuples = (('Generate SIM sequence', self.testSIMSequence),
                      ('SIM diff. angle', self.setDiffractionAngle), )
        # Store as ordered dict for easy item->func lookup.
        self.menuItems = OrderedDict(menuTuples)


    def initialize(self):
        uri = "PYRO:pyroSLM@%s:%d" % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)
        self.async = Pyro4.Proxy(uri)
        self.async._pyroAsync()
        # If there's a diffraction angle in the config, set it on the remote.
        if config.has_option(CONFIG_NAME, 'diffractionAngle'):
            theta = config.get(CONFIG_NAME, 'diffractionAngle')
            self.connection.set_sim_diffraction_angle(diffractionAngle)


    def disable(self):
        self.connection.stop()
        if self.elements.get('triggerButton'):
            self.elements['triggerButton'].Disable()


    def enable(self):
        """Enable the SLM.

        Often, after calling connection.run(), the SLM pattern and the image
        index reported are not synchronised until a few triggers have been
        sent, so we need to compensate for this. We do the best we can,
        but any other trigger-device activity during this call can mean that
        we miss the target frame by +/- 1.
        """
        # A function to trigger now.
        triggerNow = self.getTriggerFunction()
        # Target position
        if self.lastParms == self.connection.get_sequence_parameters():
            # Hardware and software sequences match
            targetPosition = self.position
        else:
            targetPosition = 0
        # Enable the hardware.
        self.connection.run()
        # Send a few triggers to clear synch. errors.
        for i in xrange(3):
            triggerNow()
            time.sleep(0.01)
        # Cycle to the target position.
        pos = self.getCurrentPosition()
        delta = (targetPosition - pos) + (targetPosition < pos) * len(self.lastParms)
        for i in xrange(delta):
            triggerNow()
            time.sleep(0.01)
        # Update the display.
        if self.elements.get('triggerButton'):
            self.elements['triggerButton'].Enable()


    def examineActions(self, name, table):
        # Extract pattern parameters from the table.
        # patternParms is a list of tuples (angle, phase, wavelength)
        patternParams = [row[2] for row in table if row[1] is self.executor]
        if not patternParams:
            # SLM is not used in this experiment.
            return

        # Remove consecutive duplicates and position resets.
        reducedParams = [p[0] for p in groupby(patternParams)
                          if type(p[0]) is tuple]
        # Find the repeating unit in the sequence.
        sequenceLength = len(reducedParams)
        for length in range(2, len(reducedParams) / 2):
            if reducedParams[0:length] == reducedParams[length:2*length]:
                sequenceLength = length
                break
        sequence = reducedParams[0:sequenceLength]
        ## Tell the SLM to prepare the pattern sequence.
        asyncResult = self.async.set_sim_sequence(sequence)

        # Step through the table and replace this handler with triggers.
        # Identify the SLM trigger(provided elsewhere, e.g. by DSP)
        triggerHandler = self.getTriggerHandler()

        # Track sequence index set by last set of triggers.
        lastIndex = 0
        for i, (t, handler, action) in enumerate(table.actions):
            if handler is not self.executor:
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
            dt = self.settlingTime + 2 * numTriggers * table.toggleTime
            ## Shift later table entries to allow for triggers and settling.
            table.shiftActionsBack(time, dt)
            for trig in xrange(numTriggers):
                t = table.addToggle(t, triggerHandler)
                t += table.toggleTime
            """
            for trig in xrange(numTriggers):
                t = table.addToggle(t, triggerHandler)
                t += table.toggleTime

            lastIndex += numTriggers
            if lastIndex >= sequenceLength:
                lastIndex = lastIndex % sequenceLength
        table.clearBadEntries()
        # Wait until SLM has finished generating and loading patterns.
        self.wait(asyncResult, "SLM is generating pattern sequence.")
        # Store the parameters used to generate the sequence.
        self.lastParms = sequence
        self.connection.run()
        # Fire several triggers to ensure that the sequence is loaded.
        triggerNow = self.getTriggerHandler().callbacks.get('triggerNow')
        for i in range(12):
            triggerNow()
            time.sleep(0.01)
        # Ensure that we're at position 0.
        self.position = self.getCurrentPosition()
        while self.position != 0:
            triggerNow()
            time.sleep(0.01)
            self.position = self.getCurrentPosition()


    ## Run some lines from the table.
    # Note we ignore the repDuration parameter, on the assumption that we
    # will never be responsible for gating the duration of a rep.
    def executeTable(self, name, table, startIndex, stopIndex, numReps,
            repDuration):
        for time, handler, action in table[startIndex:stopIndex]:
            if handler is self.executor:
                # Shouldn't have to do anything here.
                pass
        events.publish('experiment execution')


    def getCurrentPosition(self):
        return self.connection.get_current_image_index()


    def getHandlers(self):
        result = []
        # We need to be able to go over experiments to check on the
        # exposure times needed.
        self.executor = handlers.executor.ExecutorHandler(
                "slm executor",
                "slm",
                {'examineActions': self.examineActions,
                    'getNumRunnableLines': self.getNumRunnableLines,
                    'executeTable': self.executeTable,})
                    # If we add makeUI to the handler, it will be called twice:
                    # once from the device, and once from the handler. We could catch
                    # it, but shouldn't have to: abstraction is broken. We should
                    # decide whether handlers or devices are responsible for drawing
                    # UI.
                    #'makeUI': self.makeUI})
        self.executor.callbacks['getMovementTime'] = self.getMovementTime
        result.append(self.executor)
        return result


    ## Return the number of lines of the table we can execute.
    def getNumRunnableLines(self, name, table, curIndex):
        total = 0
        for time, handler, parameter in table[curIndex:]:
            if handler is not self.executor:
                return total
            total += 1


    def getTriggerHandler(self):
        return depot.getHandlerWithName(CONFIG_NAME + ' trigger')


    def getTriggerFunction(self, button=None):
        """Returns a function to step the SLM, or None."""
        triggerHandler = self.getTriggerHandler()
        if not triggerHandler:
            return None
        triggerFunc = triggerHandler.callbacks.get('triggerNow' or None)
        if not triggerFunc:
            return None

        def func(event=None):
            """Trigger the SLM once, flashing a toggle button if provided."""
            # Minimun time to flash the button.
            dtMin = 0.1
            # Button is found in outer scope.
            if button:
                button.activate()
                button.Update()
                # Store the current time.
                t0 = time.time()
            # Fire the trigger.
            triggerFunc()
            if button:
                # Ensure the button was lit long enough to be seen.
                dt = time.time() - t0
                if dt < dtMin:
                    time.sleep(dtMin - dt)
                button.deactivate()

        return func


    def getMovementTime(self):
        return self.settlingTime + 2 * actionTable.ActionTable.toggleTime


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetDoubleBuffered(True)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(
                parent=self.panel, label='SLM')
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.VERTICAL)
        self.elements = OrderedDict()
        powerButton = gui.toggleButton.ToggleButton(
                label='OFF',
                activateAction = self.enable,
                deactivateAction = self.disable,
                activeLabel = 'ON',
                inactiveLabel = 'OFF',
                parent=self.panel,
                size=gui.device.DEFAULT_SIZE)
        self.elements['powerButton'] = powerButton
        # Add a trigger button if we can trigger the SLM on demand.
        triggerButton = gui.toggleButton.ToggleButton(
                label='step',
                parent=self.panel,
                size=gui.device.DEFAULT_SIZE)
        triggerFunc = self.getTriggerFunction(triggerButton)
        if triggerFunc:
            triggerButton.Bind(wx.EVT_LEFT_DOWN, triggerFunc)
            self.elements['triggerButton'] = triggerButton
            triggerButton.Disable()
        # Add a position display.
        posDisplay = gui.device.MultilineDisplay(parent=self.panel, numLines=3)
        posDisplay.Bind(wx.EVT_TIMER,
                        lambda event: self.updatePositionDisplay(event))
        # Set up a timer to update value displays.
        self.updateTimer = wx.Timer(posDisplay)
        self.updateTimer.Start(1000)
        self.elements['posDisplay'] = posDisplay

        # Changed my mind. SIM diffraction angle is an advanced parameter,
        # so it now lives in a right-click menu rather than on a button.
        for e in self.elements.itervalues():
            e.Bind(wx.EVT_RIGHT_DOWN, lambda event: self.onRightMouse(event))
            rowSizer.Add(e)
        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        self.hasUI = True
        return self.panel


    def updatePositionDisplay(self, event):
        baseStr = 'angle:\t%d\nphase:\t%d\nwavel.:\t%d'
        # Get the display object. It seems there is variation between
        # wx versions. With some versions, the display is obtained by
        #    event.GetEventObject().
        # With others, it is
        #    event.GetEventObject().GetOwner()
        display = event.GetEventObject()
        if not hasattr(display, 'SetLabel'):
            display = display.GetOwner()
        try:
            parms = self.lastParms[self.position]
        except (IndexError, TypeError):
            # SLM parms updated since last position fetched, or lastParms is None.
            parms = None
        if parms:
            display.SetLabel(baseStr % parms)
        isPowered = self.connection.get_power()
        self.elements['powerButton'].updateState(isPowered)
        if isPowered:
            self.elements['triggerButton'].Enable()
        else:
            self.elements['triggerButton'].Disable()
        # Dispatch a call in new thread to fetch new values for next time
        self.updatePosition()


    @util.threads.callInNewThread
    def updatePosition(self):
        if not self.lastParms:
            self.lastParms = self.connection.get_sequence_parameters()
        self.position = self.getCurrentPosition()


    def onPrepareForExperiment(self, *args):
        self.position = self.getCurrentPosition()
        if 'powerButton' in self.elements:
            self.wasPowered = self.elements['powerButton'].isActive


    def cleanupAfterExperiment(self, *args):
        powerButton = self.elements['powerButton']
        if not self.wasPowered:
            # SLM was not active prior to experiment.
            if 'powerButton' in self.elements:
                self.elements['powerButton'].deactivate()
            else:
                self.disable()


    def performSubscriptions(self):
        #events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment', self.cleanupAfterExperiment)


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
        menu = gui.device.Menu(self.menuItems.keys(), self.menuCallback)
        menu.show(event)


    def testSIMSequence(self):
        inputs = gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                self.panel,
                'Generate a SIM sequence',
                ['wavelength',
                 'total angles',
                 'total phases',
                 'order\n0 for a then ph\n1 for ph then a'],
                 (488, 3, 5, 0))
        wavelength, angles, phases, order = [int(i) for i in inputs]
        if order == 0:
            params = [(theta, phi, wavelength)
                            for phi in xrange(phases)
                            for theta in xrange(angles)]
        elif order == 1:
            params = [(theta, phi, wavelength)
                            for theta in xrange(angles)
                            for phi in xrange(phases)]
        else:
            raise ValueError('Order must be 0 or 1.')
        ## Tell the SLM to prepare the pattern sequence.
        asyncResult = self.async.set_sim_sequence(params)
        self.wait(asyncResult, "SLM is generating pattern sequence.")
        self.lastParms = params


    def setDiffractionAngle(self):
        try:
            theta = self.connection.get_sim_diffraction_angle()
        except:
            raise Exception('Could not communicate with SLM service.')
        newTheta = gui.dialogs.getNumberDialog.getNumberFromUser(
                self.panel,
                'Set SIM diffraction angle',
                ('Adjust diffraction angle to\nput spots at edge of pupil.\n'
                 u'Current angle is %.2f°.' % theta ),
                theta,
                atMouse=True)
        self.connection.set_sim_diffraction_angle(newTheta)
