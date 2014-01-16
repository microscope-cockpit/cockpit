import decimal

## This class represents the actions performed during an experiment.
# Each action has a timestamp and the parameters for the action to be performed.
class ActionTable:
    def __init__(self):
        ## List of (time, handler, parameter) tuples indicating what actions
        # must be taken at what times.
        self.actions = []
    

    ## Insert an element into self.actions.
    def addAction(self, time, handler, parameter):
        self.actions.append((time, handler, parameter))
        return time


    ## Like addDigital, but rapidly toggle the output on and then off.
    # Return the time after the toggle is completed.
    def addToggle(self, time, handler):
        self.actions.append((time, handler, True))
        time += decimal.Decimal('.1')
        self.actions.append((time, handler, False))
        return time


    ## Retrieve the last time and action we performed with the specified
    # handler.
    # NB assumes that self.actions has been sorted.
    def getLastActionFor(self, handler):
        for time, altHandler, parameter in reversed(self.actions):
            if altHandler is handler:
                return time, parameter
        return None, None


    ## Sort all the actions in the table by time.
    # \todo We should remove redundant entries in here (e.g. due to 
    # 0 stabilization time for stage movement). 
    def sort(self):
        # Since the first element in each action is the timestamp, this
        # naturally sorts by time.
        self.actions.sort()


    ## Clear invalid entries from the list. Sometimes when the table is
    # modified, an entry needs to be deleted without affecting indexing into
    # the list; thus, the user sets it to None and then calls this function
    # afterwards.
    def clearBadEntries(self):
        pairs = [item for item in enumerate(self.actions)]
        for i, action in reversed(pairs):
            if action is None:
                del self.actions[i]


    ## Go through the table and ensure all timepoints are positive.
    # NB assumes the table has been sorted.
    def enforcePositiveTimepoints(self):
        delta = -self.actions[0][0]
        if delta < 0:
            # First event is at a positive time, so we're good to go.
            return
        for i in xrange(len(self.actions)):
            self.actions[i] = (self.actions[i][0] + delta,
                    self.actions[i][1], self.actions[i][2])


    ## Move all actions after the specified time back by the given offset,
    # to make room for some new action.
    def shiftActionsBack(self, markTime, delta):
        for i, (actionTime, handler, action) in enumerate(self.actions):
            if actionTime >= markTime:
                self.actions[i] = (actionTime + delta, handler, action)


    ## Return the time of the first and last action we have.
    def getFirstAndLastActionTimes(self):
        firstTime = lastTime = None
        for actionTime, handler, action in self.actions:
            if firstTime is None:
                firstTime = lastTime = actionTime
            firstTime = min(firstTime, actionTime)
            lastTime = max(lastTime, actionTime)
        return firstTime, lastTime


    ## Access an element in the table.
    def __getitem__(self, index):
        return self.actions[index]


    ## Modify an item in the table
    def __setitem__(self, index, val):
        self.actions[index] = val


    ## Get the length of the table.
    def __len__(self):
        return len(self.actions)


    ## Generate pretty text for our table, optionally only for the specified
    # handler(s)
    def prettyString(self, handlers = []):
        result = ''
        for event in self.actions:
            if event is None:
                result += '<Deleted event>\n'
            else:
                time, handler, action = event
                if not handlers or handler in handlers:
                    result += '%8.2f % 20s % 20s' % (time, handler.name, action)
                    result += '\n'
        return result


    ## Cast to a string -- generate a textual description of our actions.
    def __repr__(self):
        return self.prettyString()


    def __len__(self):
        return len(self.actions)
