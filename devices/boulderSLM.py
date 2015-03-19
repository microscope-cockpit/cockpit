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


    def initialize(self):
        uri = "PYRO:pyroSLM@%s:%d" % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)


    def enable(self):
        self.connection.run()


    def disable(self):
        self.connection.stop()


    def examineActions(self, name, table):
        # Find the SLM trigger (provided elsewhere, e.g. by DSP)
        triggerHandler = depot.getHandlerWithName(CONFIG_NAME + ' trigger')
        # Step through the table
        lastPosition = 0
        for i, (time, handler, action) in enumerate(table.actions):
            # action specifies a target frame in the sequence.
            if handler is not self.executor:
                # Nothing to do
                continue
            ## Replace entry with triggers
            # Remove original action.
            table[i] = None
            table.clearBadEntries()
            # How many triggers?
            if type(action) is int:
                numTriggers = action - lastPosition
            else:
                numTriggers = 1
            # How long will they take?
            # Time between triggers must be > table.toggleTime.
            dt = self.settlingTime + 2 * numTriggers * table.toggleTime
            ## Shift later table entries to allow for triggers and settling.
            table.shiftActionsBack(time, dt)
            for trig in xrange(numTriggers):
                time = table.addToggle(time, triggerHandler)
                time += table.toggleTime
            lastPosition += numTriggers


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


    def performSubscriptions(self):
        #events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        #events.subscribe('cleanup after experiment',
        #        self.cleanupAfterExperiment)


    def onPrepareForExperiment(self, *args):
        self.position = self.getCurrentPosition()
