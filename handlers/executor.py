import depot
import deviceHandler



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


    def examineActions(self, table):
        return self.callbacks['examineActions'](self.name, table)


    def getNumRunnableLines(self, table, index):
        return self.callbacks['getNumRunnableLines'](self.name, table, index)


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


