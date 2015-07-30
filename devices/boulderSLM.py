""" This module makes a BNS SLM  device available to Cockpit.

Mick Phillips, University of Oxford, 2014.
Historically, a single CameraDevice was used to address multiple
cameras, using a number of dictionaries to map the camera name to
its settings and methods.  Here, instead I have used a single
CameraManager to keep track of one or more CameraDevices, which
means that inheritance can be used for different camera types.

All the handler functions are called with (self, name, *args...).
Since we make calls to instance methods here, we don't need 'name',
but it is left in the call so that we can continue to use camera
modules that rely on dictionaries.

Cockpit uses lowerCamelCase function names.
Functions names as lower_case are remote camera object methods.
"""

import decimal
import depot
import device
from itertools import groupby
import Pyro4
import wx

import events
import gui.guiUtils
import gui.toggleButton
import handlers
from config import config

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
        self.executor = None
        self.order = None
        self.position = None
        self.settlingTime = decimal.Decimal('0.01')
        self.slmTimeout = int(config.get(CONFIG_NAME, 'timeout', default=10))
        self.slmRetryLimit = int(config.get(CONFIG_NAME, 'retryLimit', default=3))


    def initialize(self):
        uri = "PYRO:pyroSLM@%s:%d" % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)


    def disable(self):
        self.connection.stop()


    def enable(self):
        self.connection.run()


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
        asyncProxy = Pyro4.async(self.connection)
        asyncResult = asyncProxy.set_sim_sequence(sequence)

        # Step through the table and replace this handler with triggers.
        # Identify the SLM trigger(provided elsewhere, e.g. by DSP)
        triggerHandler = depot.getHandlerWithName(CONFIG_NAME + ' trigger')
        # Track sequence index set by last set of triggers.
        lastIndex = 0
        for i, (time, handler, action) in enumerate(table.actions):
            if handler is not self.executor:
                # Nothing to do
                continue
            # Action specifies a target frame in the sequence.
            # Remove original event.
            table[i] = None
            table.clearBadEntries()
            # How many triggers?
            if type(action) is tuple and action != sequence[lastIndex]:
                # Next pattern does not match last, so step one pattern.
                    numTriggers = 1
            elif type(action) is int:
                if action > lastIndex:
                    numTriggers = action - lastIndex
                else:
                    numTriggers = sequenceLength - lastIndex - action
            else:
                numTriggers = 0
            # How long will the triggers take?
            # Time between triggers must be > table.toggleTime.
            dt = self.settlingTime + 2 * numTriggers * table.toggleTime
            ## Shift later table entries to allow for triggers and settling.
            table.shiftActionsBack(time, dt)
            for trig in xrange(numTriggers):
                time = table.addToggle(time, triggerHandler)
                time += table.toggleTime
            # Update index tracker.
            lastIndex += numTriggers
            if lastIndex >= sequenceLength:
                lastIndex = lastIndex % sequenceLength
            
        # Wait unti the SLM has finished preparing the pattern sequence.
        status = wx.ProgressDialog(parent = wx.GetApp().GetTopWindow(),
                title = "Waiting for SLM",
                message = "SLM is generating pattern sequence.")
        status.Show()
        slmFailCount = 0
        slmFail = False
        while not asyncResult.wait(timeout=self.slmTimeout) and not slmFail:
            slmFailCount += 1
            if slmFailCount >= self.slmRetryLimit:
                slmFail = True
        status.Destroy()
        if slmFail:
            raise Exception('SLM set_sim_sequence timeout.')
        self.connection.run()


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
                    'executeTable': self.executeTable})
        result.append(self.executor)
        return result


    ## Return the number of lines of the table we can execute.
    def getNumRunnableLines(self, name, table, curIndex):
        total = 0
        for time, handler, parameter in table[curIndex:]:
            if handler is not self.executor:
                return total
            total += 1


    def onPrepareForExperiment(self, *args):
        self.position = self.getCurrentPosition()


    def performSubscriptions(self):
        #events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        #events.subscribe('cleanup after experiment',
        #        self.cleanupAfterExperiment)