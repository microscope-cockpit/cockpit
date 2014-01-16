import depot
import device
import events
import handlers.executor
import handlers.lightSource
import util.logger

import decimal
import re
import telnetlib

CLASS_NAME = 'DigitalDelayGeneratorDevice'



## This class communicates with the digital delay generator, which we use to 
# provide access to some light sources with very fine time resolution.
class DigitalDelayGeneratorDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = True
        ## Telnet connection to the device.
        self.connection = None
        ## IP address of the device.
        self.ipAddress = '192.168.12.90'
        ## Set of handlers we control.
        self.handlers = set()
        ## Our ExperimentExecutor handler.
        self.executor = None
        ## Cached exposure times we have set.
        self.nameToExposureTime = {}
        ## Cached trigger response delay
        self.curDelay = None
        ## Set of handlers for lights we actually control.
        self.controlledLights = set()
        events.subscribe('prepare for experiment', self.prepareForExperiment)
        events.subscribe('experiment complete', self.cleanupAfterExperiment)


    ## Connect to the device.
    def initialize(self):
        self.connection = telnetlib.Telnet(self.ipAddress, 5024, timeout = 5)
        self.connection.read_until("DG645 Telnet Session:")
        # Read out any trailing whitespace, e.g. newlines.
        self.connection.read_eager()
        # Allow some time for other devices to keep up when we take images
        # in interactive mode (i.e. hitting the '+' key).
        self.setInitialDelay(1)


    def finalizeInitialization(self):
        for name in ['488 Deepstar']:
            self.controlledLights.add(depot.getHandlerWithName(name))
            

    ## We return one handler for each light source we control, plus an
    # experiment executor.
    def getHandlers(self):
        result = []
        # We need to be able to go over experiments to check on the 
        # exposure times needed.
        self.executor = handlers.executor.ExecutorHandler(
                "delay generator executor",
                "delay generator",
                {'examineActions': self.examineActions,
                    'getNumRunnableLines': self.getNumRunnableLines,
                    'executeTable': self.executeTable})
        result.append(self.executor)
        return result


    ## Write raw text to the connection, and return the result. We read until
    # we hit a newline or a short time passes, to allow for functions that
    # have no return value.
    def sendCommand(self, command):
        self.connection.write(command + '\n')
        return self.connection.read_until('\n', .05)
 

    ## Set the delay between receipt of external trigger and starting our own
    # signal.
    # \param delayMS Time to delay, in milliseconds.
    def setInitialDelay(self, delayMS):
        if delayMS != self.curDelay:
            num = convertToScientific(delayMS / 1000.0)
            # Set channel 2 to be a specific time after trigger
            self.sendCommand('DLAY2,0,%s' % num)
            self.sendCommand('LCAL')
            self.curDelay = delayMS


    ## Get the initial delay before sending a signal, in milliseconds.
    def getInitialDelay(self):
        return self.curDelay
        

    ## Set the exposure time (time between rising and falling edges).
    # \param timeUS Exposure time in microseconds
    def setExposureTime(self, name, value):
        if value != self.nameToExposureTime.get(name, None):
            num = convertToScientific(decimal.Decimal(value) / decimal.Decimal('1000'))
            # Set channel 3 to be a specific time after channel 2
            self.sendCommand('DLAY3,2,%s' % num)
            self.sendCommand('LCAL')
            self.nameToExposureTime[name] = value


    ## Get the current exposure time, in milliseconds.
    def getExposureTime(self, name):
        if name in self.nameToExposureTime:
            return self.nameToExposureTime[name]
        result = self.sendCommand('DLAY?3')
        # Result is expressed as delay after channel 2, e.g. 
        # "2+.0010000000"
        result = float(result.split('+')[1]) * 1000
        self.nameToExposureTime[name] = result
        return result


    ## Take a look at the provided table. We do two main things here. First, we
    # track exposure times so that we're set for the right output during the
    # experiment (and add actions to adjust our exposure times as needed).
    # Second, we replace uses of LightSource handlers with the DSP's
    # delayHandler object, so that we get triggered instead of opening the
    # physical shutters (which are instead left on for the duration of the
    # experiment).
    def examineActions(self, name, table):
        # Maps handlers to the last time they went up.
        handlerToActivationTime = {}
        # Maps handlers to the last-used exposure time for those handlers.
        handlerToExposureTime = {}
        # Maps handlers to new actions for those handlers.
        handlerToActions = {}
        # Time offset we're adding to each action to make room for our
        # change-exposure-time actions.
        timeOffset = 0
        lights = set(depot.getHandlersOfType(depot.LIGHT_TOGGLE))
        delayHandler = depot.getHandlerWithName('Delay generator trigger')
        for i, (time, handler, action) in enumerate(table.actions):
            if handler not in self.controlledLights:
                # Not a device we care about.
                continue
            if action:
                # Starting an exposure; add a trigger of the delay generator
                # here.
                handlerToActivationTime[handler] = time
                table.addToggle(time, delayHandler)
            else:
                # Ending an exposure; calculate duration and check if 
                # we need to change the exposure time for that line.
                if handler not in handlerToActivationTime:
                    message = "At %.2f, ending an exposure for %s without starting one" % (time, handler.name)
                    util.logger.log.error(message)
                    util.logger.log.error(str(table))
                    raise RuntimeError(message)
                duration = time - handlerToActivationTime[handler]
                if handler not in handlerToActions:
                    handlerToActions[handler] = []
                # Only care about duration variations of more than 500ns.
                if (handler not in handlerToExposureTime or 
                        abs(handlerToExposureTime[handler] - duration) > .0005):
                    action = (handlerToActivationTime[handler],
                            self.executor, (handler, duration))
                    handlerToExposureTime[handler] = duration
                    handlerToActions[handler].append(action)
            # Remove the event since it'll be replaced by triggering the
            # delay generator.
            table[i] = None

        table.clearBadEntries()
        # If we only have at most one new action (i.e. new exposure time) per
        # handler, then we can just set their exposure times in advance;
        # otherwise we have to interrupt the experiment, set the new time,
        # and then continue.
        for i, (handler, actions) in enumerate(handlerToActions.iteritems()):
            if len(actions) == 1:
                self.setExposureTime(handler.name, handlerToExposureTime[handler])
            else:
                for actionTime, handler, parameter in actions:
                    # Take into account previous actions we've inserted.
                    actionTime = actionTime + i * decimal.Decimal('.1')
                    # We have to make room for the new action, by pushing
                    # everything else back a bit.
                    table.shiftActionsBack(actionTime, decimal.Decimal('.1'))
                    table.addAction(actionTime, handler, parameter)
        # In any case, leave all lights open for the duration of the experiment.
        start, end = table.getFirstAndLastActionTimes()
        for handler in handlerToActions.keys():
            table.addAction(start, handler, True)
            table.addAction(end, handler, False)


    ## Return the number of lines of the table we can execute.
    def getNumRunnableLines(self, name, table, curIndex):
        total = 0
        for time, handler, parameter in table[curIndex:]:
            if handler is not self.executor:
                return total
            total += 1


    ## Run some lines from the table.
    # Note we ignore the repDuration parameter, on the assumption that we 
    # will never be responsible for gating the duration of a rep.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        for time, handler, action in table[startIndex:stopIndex]:
            if handler is self.executor:
                # Set exposure time for one of our light sources.
                light, exposureTime = action
                self.setExposureTime(light.name, exposureTime)
        events.publish('experiment execution')


    ## Get ready for an experiment: set the initial trigger delay to 0.
    def prepareForExperiment(self, experiment):
        self.setInitialDelay(0)


    ## Experiment finished; set the delay back to 1ms so that other
    # devices can keep up.
    def cleanupAfterExperiment(self):
        self.setInitialDelay(1)


    ## Switch the delay generator "on" (front panel active and listening to 
    # external trigger) and "off" (front panel inactive and listening to 
    # internal trigger).
    def setIsActive(self, isActive):
        if isActive:
            # Trigger on external rising edge
            self.sendCommand('TSRC1')
            # Show the display
            self.sendCommand('SHDP1')
        else:
            # Trigger on internal
            self.sendCommand('TSRC0')
            # Hide the display
            self.sendCommand('SHDP0')
        self.sendCommand('LCAL')



## Convert an input floating point number to scientific notation in the form
# "XYZe-N". Note the lack of decimal point -- the DDG doesn't allow them.
# Annoyingly, Python's built-in scientific notation doesn't work directly 
# either, though it's a good starting point. We just need to merge the bits
# before and after the decimal and decrement the exponent.
def convertToScientific(val):
    # Convert to Python scientific (A.BCDEF0000e-N)
    strVal = "%e" % val
    # Split out the components before/after the decimal and the
    # exponent.
    match = re.search(r'(\d)\.(\d+)e(.*)', strVal)
    first, rest, exponent = match.groups()
    # Strip off the trailing zeros from the decimal portion.
    match = re.match(r'(.*?)0*$', rest)
    rest = match.group(1)
    if not rest:
        # No post-decimal portion.
        return '%se%d' % (first, int(exponent))
    return '%s%se%d' % (first, rest, int(exponent) - len(rest))

