import depot
import deviceHandler
import util.threads
import time

## This handler is responsible for executing portions of experiments.
class ExecutorHandler(deviceHandler.DeviceHandler):
    ## callbacks must include the following:
    # - examineActions(name, table): Perform any necessary validation or
    #   modification of the experiment's ActionTable. 
    # - getNumRunnableLines(name, table, index): Given an input ActionTable, 
    #   return the number of lines in the table that we can implement, starting
    #   from the specified index.
    # - executeTable(name, table, startIndex, stopIndex): Actually perform
    #   actions through the specified lines in the ActionTable.
    def __init__(self, name, groupName, callbacks):
        # Note that even though this device is directly involved in running
        # experiments, it is never itself a part of an experiment, so 
        # we pass False for isEligibleForExperiments here.
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False,
                callbacks, depot.EXECUTOR)
        # Base class contains empty dicts used by mixins so that methods like
        # getNumRunnableLines can be implemented here for all mixin combos.
        self.digitalClients = {}
        self.analogClients = {}
        if not isinstance(self, DigitalMixin):
            self.registerDigital = self._noDigital
            self.getDigital = self._noDigital
            self.setDigital = self._noDigital
            self.triggerDigital = self._noDigital
        if not isinstance(self, AnalogMixin):
            self.registerAnalog = self._noAnalog
            self.setAnalog = self._noAnalog
            self.getAnalog = self._noAnalog
            self.setAnalogClient = self._noAnalog
            self.getAnalogClient = self._noAnalog

    def examineActions(self, table):
        return self.callbacks['examineActions'](self.name, table)

    def getNumRunnableLines(self, table, index):
        ## Return number of lines this handler can run.
        count = 0
        for time, handler, parameter in table[index:]:
            # Check for analog and digital devices we control.
            count += 1
            if (handler is not self and
                   handler not in self.digitalClients and
                   handler not in self.analogClients):
                # Found a device we don't control.
                break
        return count

    def _noDigital(self, *args, **kwargs):
        raise Exception("Digital lines not supported.")

    def _noAnalog(self, *args, **kwargs):
        raise Exception("Analog lines not supported")

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
        return self.callbacks['executeTable'](self.name, table, startIndex, 
                stopIndex, numReps, repDuration)


class DigitalMixin(object):
    ## Register a client device that is connected to one of our lines.
    # Return a wrapped copy of self that abstracts out line.
    def registerDigital(self, client, line):
        self.digitalClients[client] = line

    def setDigital(self, line, state):
        self.callbacks['setDigital'](line, state)

    def triggerDigital(self, client, dt=0.01):
        ## Trigger a client line now.
        line = self.digitalClients.get(client, None)
        if line:
            self.setDigital(line, True)
            time.sleep(dt)
            self.setDigital(line, False)


class AnalogMixin(object):
    ## Register a client device that is connected to one of our lines.
    # Return a wrapped copy of self that abstracts out line.
    def registerAnalog(self, client, line):
        self.analogClients[client] = line

    def setAnalog(self, line, level):
        self.callbacks['setAnalog'](line, level)


class DigitalExecutorHandler(DigitalMixin, ExecutorHandler):
    pass


class AnalogExecutorHandler(AnalogMixin, ExecutorHandler):
    pass


class AnalogDigitalExecutorHandler(AnalogMixin, DigitalMixin, ExecutorHandler):
    pass