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

import decimal
import matplotlib
matplotlib.use('WXAgg')
import matplotlib.backends.backend_wxagg
import matplotlib.figure
import numpy
import Pyro4
import time
import wx

import depot

import device
import events
import gui.toggleButton
import handlers.executor
import handlers.genericHandler
import handlers.genericPositioner
import handlers.imager
import handlers.lightSource
import handlers.stagePositioner
import util.threads
from config import config, LIGHTS, CAMERAS, AOUTS
CLASS_NAME = 'DSPDevice'
COCKPIT_AXES = {'x': 0, 'y': 1, 'z': 2}#, 'SI angle': -1}
CONFIG_NAME = 'dsp'

class DSPDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        if not self.isActive:
            return
        ## IP address of the DSP computer.
        self.ipAddress = config.get('dsp', 'ipAddress')
        ## Port to use to connect to the DSP computer.
        self.port = int(config.get('dsp', 'port'))
        ## Connection to the remote DSP computer
        self.connection = None
        ## Set of all handlers we control.
        self.handlers = set()
        ## Where we believe the stage piezos to be.
        self.curPosition = {}
        ## Names of cameras we trigger when taking an image.
        self.activeCameras = set()
        ## Names of light sources we trigger when taking an image.
        self.activeLights = set()
        ## Maps light source names to exposure times for those lights.
        self.lightToExposureTime = {}
        ## Maps various handlers to the digital lines we use to trigger that
        # handler.
        self.handlerToDigitalLine = {}
        ## Maps various handlers to the analog axes we use to manipulate them.
        self.handlerToAnalogLine = {}
        ## Maps handler names to the digital lines we use to activate those
        # devices. 
        self.nameToDigitalLine = {}
        self.nameToDigitalLine.update({key: val['triggerLine'] for \
                                       key, val in LIGHTS.iteritems()})
        self.nameToDigitalLine.update({key: val['triggerLine'] for \
                                       key, val in CAMERAS.iteritems()})
        self.otherTriggers = []
        for s in config.sections():
            if not config.has_option(s, 'triggerLine'):
                continue
            t = int(config.get(s, 'triggerLine'))
            name = '%s trigger' % s
            self.nameToDigitalLine.update({name: 1 << t})
            self.otherTriggers.append(name)
        ## Resolution of actions we can take when running experiments.
        self.actionsPerMillisecond = 10
        ## Conversion factor between microns and the units the DSP card
        # uses. The DSP has a 16-bit DAC (so 65536 ADUs (analog-digital units)
        # representing 0-10 volts).
        self.alineToUnitsPerADU = {}
        self.axisMapper = {}
        VperADU = 10.0 / 2**16
        for key, aout in AOUTS.iteritems():
            self.alineToUnitsPerADU.update({\
                aout['aline']: aout['sensitivity'] * VperADU, })
            ## Maps Cockpit axes (0: X, 1: Y, 2: Z) to DSP analog lines
            if aout['cockpit_axis'] in 'xyzXYZ':
                self.axisMapper.update({\
                    COCKPIT_AXES[aout['cockpit_axis']]: int(aout['aline']), })
        
        ## Position tuple of the piezos prior to experiment starting.
        self.preExperimentPosition = None
        ## (profile, digital settings, analog settings) tuple describing
        # the last Profile we loaded onto the DSP card.
        self.prevProfileSettings = None
        ## Digital values as of the end of the last profile we sent to the
        # card, so we can recall them later.
        self.lastDigitalVal = 0
        ## Analog positions as of the end of the last profile we sent to the
        # card, so that it doesn't re-baseline values in the middle of an
        # experiment.
        self.lastAnalogPositions = [0] * 4
        ## Values for anologue positions at startup.
        self.startupAnalogPositions = [None] * 4
		#IMD 20150617 adeded to make adcanved control work.
        self.makeOutputWindow = makeOutputWindow
        self.buttonName='DSP TTL'


    ## Connect to the DSP computer.
    @util.threads.locked
    def initialize(self):
        uri = 'PYRO:pyroDSP@%s:%d' % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)
        self.connection._pyroTimeout = 6
        self.connection.Abort()


    ## We care when cameras are enabled, since we control some of them 
    # via external trigger. There are also some light sources that we don't
    # control directly that we need to know about.
    def performSubscriptions(self):
        events.subscribe('camera enable', self.toggleCamera)
        events.subscribe('light source enable', self.toggleLightHandler)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)

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
        events.publish("DSP done")


    @util.threads.locked
    def finalizeInitialization(self):
        # Tell the remote DSP computer how to talk to us.
        server = depot.getHandlersOfType(depot.SERVER)[0]
        uri = server.register(self.receiveData)
        self.connection.receiveClient(uri)
        # Get all the other devices we can control, and add them to our
        # digital lines.
        for name, line in self.nameToDigitalLine.iteritems():
            handler = depot.getHandlerWithName(name)
            if handler is not None:
                self.handlerToDigitalLine[handler] = line

        # Move analogue lines to initial positions, if given in config.
        for handler, line in self.handlerToAnalogLine.iteritems():
            pos = self.startupAnalogPositions[line]
            if pos is not None:
                handler.moveAbsolute(pos)


    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        # The "Ambient" light source lets us specify exposure times for images
        # with no active illumination.
        for key, light in LIGHTS.iteritems():
            # Set up lightsource handlers with default 100ms expsure time.
            handler = handlers.lightSource.LightHandler(
                light['label'], "%s light source" % light['label'],
                {'setEnabled': self.toggleLight,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime},
                light['wavelength'],
                100)    
            self.lightToExposureTime[handler.name] = 100
            self.handlerToDigitalLine[handler] = light['triggerLine']
            result.append(handler)

        for key, aout in AOUTS.iteritems():
            if aout['cockpit_axis'] in 'xyzXYZ':
                axisName = COCKPIT_AXES[aout['cockpit_axis'].lower()]
                handler = handlers.stagePositioner.PositionerHandler(
                    "%s piezo" % axisName, "%s stage motion" % axisName, True, 
                    {'moveAbsolute': self.movePiezoAbsolute,
                        'moveRelative': self.movePiezoRelative, 
                        'getPosition': self.getPiezoPos, 
                        'getMovementTime': self.getPiezoMovementTime,
                        'cleanupAfterExperiment': self.cleanupPiezo,
                        # The DSP doesn't have modifiable soft motion safeties.
                        'setSafety': lambda *args: None},
                    COCKPIT_AXES[aout['cockpit_axis']], 
                    aout['deltas'],
                    aout['default_delta'],
                    aout['hard_limits'])
                self.handlerToAnalogLine[handler] = int(aout['aline'])#COCKPIT_AXES[aout['cockpit_axis']]
                result.append(handler)
                self.curPosition.update({COCKPIT_AXES[aout['cockpit_axis']]: 0})
                self.startupAnalogPositions[aout['aline']] = aout.get('startup_value')
                
        for name in self.otherTriggers:
            handler = handlers.genericHandler.GenericHandler(
                name, 'other triggers', True,
                callbacks = {'triggerNow': lambda: self.triggerNow(self.nameToDigitalLine[name]),})
            self.handlerToDigitalLine[handler] = self.nameToDigitalLine[name]
            result.append(handler)

        result.append(handlers.imager.ImagerHandler(
            "DSP imager", "imager",
            {'takeImage': self.takeImage}))

        result.append(handlers.executor.ExecutorHandler(
            "DSP experiment executor", "executor",
            {'examineActions': lambda *args: None, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable,
                'registerAnalogue': self.registerAnalogueDevice},))

        self.handlers = set(result)
        return result


    ## Receive data from the DSP computer.
    def receiveData(self, action, *args):
        if action == 'DSP done':
            print "dsp done"
            events.publish("DSP done")


    ## Enable/disable a specific light source.
    def toggleLight(self, lightName, isEnabled):
        if isEnabled:
            self.activeLights.add(lightName)
        elif lightName in self.activeLights:
            self.activeLights.remove(lightName)


    def triggerNow(self, line, dt=0.01):
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)
        time.sleep(dt)
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)


    ## As toggleLight, but accepts a handler instead.
    def toggleLightHandler(self, handler, isEnabled):
        self.toggleLight(handler.name, isEnabled)


    ## Update the exposure time for a specific light source.
    def setExposureTime(self, name, value):
        self.lightToExposureTime[name] = value


    ## Retrieve the exposure time for a specific light source.
    def getExposureTime(self, name):
        return self.lightToExposureTime[name]


    ## Enable/disable a specific camera.
    def toggleCamera(self, camera, isEnabled):
        if not isEnabled and camera.name in self.activeCameras:
            self.activeCameras.remove(camera.name)
        else:
            self.activeCameras.add(camera.name)


    ## Report the new position of a piezo.
    def publishPiezoPosition(self, axis):
        events.publish('stage mover', '%d piezo' % axis, 
                axis, self.curPosition[axis])


    ## Move a stage piezo to a given position.
    def movePiezoAbsolute(self, axis, pos):
        self.curPosition.update({axis: pos})
        # Convert from microns to ADUs.
        aline = self.axisMapper[axis]
        aduPos = self.convertMicronsToADUs(aline, pos)
        self.connection.MoveAbsoluteADU(aline, aduPos)
        self.publishPiezoPosition(axis)
        # Assume piezo movements are instantaneous; we don't get notified by
        # the DSP when motion stops, anyway.
        events.publish('stage stopped', '%d piezo' % axis)


    ## Move the stage piezo by a given delta.
    def movePiezoRelative(self, axis, delta):
        self.movePiezoAbsolute(axis, self.curPosition[axis] + delta)


    ## Get the current piezo position.
    def getPiezoPos(self, axis):
        return self.curPosition[axis]


    ## Get the amount of time it would take the piezo to move from the 
    # initial position to the final position, as well
    # as the amount of time needed to stabilize after that point, 
    # both in milliseconds. These numbers are both somewhat arbitrary;
    # we just say it takes 1ms per micron to stabilize and .1ms to move.
    def getPiezoMovementTime(self, axis, start, end):
        distance = abs(start - end)
        return (decimal.Decimal('.1'), decimal.Decimal(distance * 1))


    ## Set the SLM's position to a specific value. 
    # For now, do nothing; the only way we can change the SLM position is by 
    # sending triggers so we have no absolute positioning.
    def setSLMPattern(self, name, position): 
        pass


    ## Adjust the SLM's position by the specified offset. Again, do nothing.
    def moveSLMPatternBy(self, name, delta):
        pass


    ## Get the current SLM position, either angle or phase depending on the 
    # caller. We have no idea, really.
    def getCurSLMPattern(self, name):
        return 0


    ## Get the time to move to a new SLM position, and the stabilization time, 
    # in milliseconds. Note we assume that this requires only one triggering
    # of the SLM.
    def getSLMStabilizationTime(self, name, prevPos, curPos):
        return (1, 30)

    ## Take an image with the current light sources and active cameras.
    @util.threads.locked
    def takeImage(self):
        cameraMask = 0
        lightTimePairs = []
        maxTime = 0
        for handler, line in self.handlerToDigitalLine.iteritems():
            if handler.name in self.activeLights:
                maxTime = max(maxTime, handler.getExposureTime())
                # The DSP card can only handle integer exposure times.
                exposureTime = int(numpy.ceil(handler.getExposureTime()))
                lightTimePairs.append((line, exposureTime))
                maxTime = max(maxTime, exposureTime)
        for name, line in self.nameToDigitalLine.iteritems():
            if name in self.activeCameras:
                cameraMask += line
                handler = depot.getHandlerWithName(name)
                handler.setExposureTime(maxTime)
 #       print "Cam mask, lighttimeparis", cameraMask, lightTimePairs
        self.connection.arcl(cameraMask, lightTimePairs)


    ## Prepare to run an experiment: cache our current piezo positions so
    # we can restore them afterwards. Set our remembered output values so we
    # have the correct baselines for each subset of the experiment, and set
    # our values for before the experiment starts, so they can be restored
    # at the end.
    def onPrepareForExperiment(self, *args):
        self.preExperimentPosition = self.curPosition.copy()
        self.lastDigitalVal = 0
        # Values in lastAnalogPositions are baselines for profiles.
        # Piezo handlers specify moves as deltas. Others specify
        # absolute voltages, so move these others to their start positions.
        self.lastAnalogPositions = 4 * [0]
        for h, line in self.handlerToAnalogLine.iteritems():
            if line not in self.axisMapper.values():
                h.moveAbsolute(self.startupAnalogPositions[line])
                self.lastAnalogPositions[line] = self.startupAnalogPositions[line]


    ## Cleanup after an experiment completes: restore our cached position.
    def cleanupAfterExperiment(self, *args):
        for axis, position in self.preExperimentPosition.iteritems():
            self.movePiezoAbsolute(axis, position)


    ## Get the number of actions from the provided table that we are
    # capable of executing.
    def getNumRunnableLines(self, name, table, index):
        count = 0
        for time, handler, parameter in table[index:]:
            # Check for analog and digital devices we control.
            if (handler not in self.handlers and 
                    handler.name not in self.nameToDigitalLine):
                # Found a device we don't control.
                break
            count += 1
        return count


    ## Actually execute the events in an experiment ActionTable, starting at
    # startIndex and proceeding up to but not through stopIndex.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        # Convert the desired portion of the table into a "profile" for
        # the DSP card.
        profileStr, digitals, analogs = self.generateProfile(table[startIndex:stopIndex], repDuration)
        # Update our positioning values in case we have to make a new profile
        # in this same experiment. The analog values are a bit tricky, since
        # they're deltas from the values we used to create the profile.
        self.lastDigitalVal = digitals[-1, 1]
        for aline in xrange(4):
            self.lastAnalogPositions[aline] = analogs[aline][-1][1] + self.lastAnalogPositions[aline]

        # Apologies for the messiness here; basically we're checking if any
        # aspect of the experiment profile has changed compared to the last
        # experiment we ran, if any. If there are differences, then we must
        # upload the new profile; otherwise we can skip that step.
        if (self.prevProfileSettings is None or
                profileStr != self.prevProfileSettings[0] or
                numpy.any(digitals != self.prevProfileSettings[1]) or
                sum([numpy.any(analogs[i] != self.prevProfileSettings[2][i]) for i in xrange(4)])):
            # We can't just re-use the already-loaded profile.
            self.connection.profileSet(profileStr, digitals, *analogs)
            self.connection.DownloadProfile()
            self.prevProfileSettings = (profileStr, digitals, analogs)
            
        events.publish('update status light', 'device waiting',
                'Waiting for\nDSP to finish', (255, 255, 0))
        self.connection.InitProfile(numReps)
        events.executeAndWaitFor("DSP done", self.connection.trigCollect)

        events.publish('experiment execution')
        return


    ## Clean up after experiment is done.
    def cleanupPiezo(self, axis, isCleanupFinal):
        if isCleanupFinal:
            # The DSP may complain about still being in collection mode
            # even though it's told us it's done; wait a bit.
            time.sleep(.25)
            position = self.connection.ReadPosition(self.axisMapper[axis])
            self.curPosition.update({axis: position})
            self.publishPiezoPosition(axis)
            # Manually force all digital lines to 0, because for some reason the
            # DSP isn't doing this on its own, even though our experiments end
            # with an all-zeros entry.
            self.connection.WriteDigital(0)

    ## Given a list of (time, handle, action) tuples, generate several Numpy
    # arrays: one of digital actions, and one each for each analog output.
    # We also generate the "profile string" that is used to describe these
    # arrays.
    def generateProfile(self, events, repDuration):
        # Maps digital lines to the most recent setting for that line.
        digitalToLastVal = {}
        # Maps analog lines to lists of (time, value) pairs. 
        analogToPosition = {}
        
        # Expand out the timepoints so we can use integers to refer to 
        # sub-millisecond events, since the DSP table doesn't use
        # floating point.
        # Convert from decimal.Decimal instances to floating point.
        times = [float(e[0] * self.actionsPerMillisecond) for e in events]
        # Now convert to int while rounding. The rounding is necessary,
        # otherwise e.g. 10.1 and 10.1999999... both result in 101.
        times = [int(t + .5) for t in times]
        times = sorted(list(set(times)))
        baseTime = times[0]
        # Take into account the desired rep duration -- if we have spare
        # time left over, then we insert a dummy action in to take up that
        # spare time.
        if repDuration is not None:
            repDuration *= self.actionsPerMillisecond
            waitTime = repDuration - (times[-1] - baseTime)
            if waitTime > 0:
                times.append(baseTime + repDuration)
        # HACK: ensure that there's at least 2 timesteps in the experiment,
        # or else it won't run properly.
        havePaddedDigitals = False
        if len(times) == 1:
            times.append(times[0] + 1)
            havePaddedDigitals = True
            
        digitals = numpy.zeros((len(times), 2), dtype = numpy.uint32)
        digitals[:, 0] = times
        # Rebase the times so that they start from 0.
        digitals[:, 0] -= baseTime

        # Construct lists of (time, value) pairs for the DSP's digital and
        # analog outputs.
        curDigitalValue = self.lastDigitalVal
        alineToAnalogs = {}
        # Keep track of last action time and handler to detect conflicts.
        lastTime = None
        lastHandler = None
        lastAction = None
        for time, handler, action in events:
            # Do the same "Decimal -> float -> rounded int" conversion
            time = int(float(time * self.actionsPerMillisecond) + .5)
            # Ensure that we don't try to do two actions with the same
            # handler on the same clock - if we do, the second action will
            # be lost.
            if time  == lastTime and handler == lastHandler:
                if action != lastAction:
                    # This is not just a duplicate table entry.
                    raise Exception('%s: Simultaneous actions with handler %s at time %s' %
                                     (CONFIG_NAME, handler, time))
            lastTime = time
            lastHandler = handler
            lastAction = action
            index = times.index(time)
            # Ensure a valid (nonzero) digital value exists regardless of the
            # type of action, e.g. so analog actions don't zero the digital
            # output.
            digitals[index, 1] = curDigitalValue
            if handler in self.handlerToDigitalLine:
                # Update curDigitalValue according to the value of the output
                # line for this handler. Digital actions are either on or off,
                # and they stay that way until told otherwise.
                line = self.handlerToDigitalLine[handler]
                if line not in digitalToLastVal or digitalToLastVal[line] != action:
                    # Line has changed
                    addend = line
                    if not action:
                        addend = -line
                    if curDigitalValue + addend < 0:
                        # This should never happen.
                        raise RuntimeError("Negative current digital value from adding %s to %s" % (bin(addend), bin(curDigitalValue)))
                    curDigitalValue += addend
                    digitals[index, 1] = curDigitalValue
                digitalToLastVal[line] = action
            elif handler in self.handlerToAnalogLine:
                # Analog lines step to the next position. 
                aline = self.handlerToAnalogLine[handler]
                value = 0
                value = self.convertMicronsToADUs(aline, action)
                # If we're in the
                # middle of an experiment, then these values need to be
                # re-baselined based on where we started from, since when the
                # DSP treats all analog positions as offsets of where it was
                # when it started executing the profile.
                value -= self.lastAnalogPositions[aline]
                if aline not in alineToAnalogs:
                    alineToAnalogs[aline] = []
                alineToAnalogs[aline].append((time - baseTime, value))
            else:
                raise RuntimeError("Unhandled handler when generating DSP profile: %s" % handler.name)

        if havePaddedDigitals:
            # We created a dummy digitals entry since there was only one
            # timepoint, but that dummy entry has an output value of 0 instead
            # of whatever the current output is, so replace it.
            digitals[-1, 1] = curDigitalValue

        # Convert the analog actions into Numpy arrays now that we know their
        # lengths. Default to [0, 0], fill in a proper array for any axis where
        # we actually do something.
        analogs = [numpy.zeros((1, 2), dtype = numpy.uint32) for i in xrange(4)]
        for aline, actions in alineToAnalogs.iteritems():
            analogs[aline] = numpy.zeros((len(actions), 2), dtype = numpy.uint32)
            for i, (time, value) in enumerate(actions):
                analogs[aline][i] = (time, value)

        # HACK: if the last analog action comes at the same time as, or after,
        # the last digital action, then we need to insert a dummy digital
        # action, or else the last analog action (or possibly all analog
        # actions after the last digital action) will not be performed. No,
        # I have no idea why this is.
        lastAnalogTime = max([a[-1, 0] for a in analogs])
        if lastAnalogTime >= digitals[-1, 0]:
            # Create a new array for the digital entries.
            temp = numpy.ones((digitals.shape[0] + 1, 2), dtype = digitals.dtype)
            # Fill in the old values
            temp[:-1] = digitals
            # Create a dummy action.
            temp[-1] = [lastAnalogTime + 1, curDigitalValue]
            digitals = temp

        # Generate the string that describes the profile we've created.
        description = numpy.rec.array(None,
                formats = "u4, f4, u4, u4, 4u4",
                names = ('count', 'clock', 'InitDio', 'nDigital', 'nAnalog'),
                aligned = True, shape = 1)

        runtime = max(digitals[:, 0])
        for aline in xrange(4):
            runtime = max(runtime, max(analogs[aline][:, 0]))
        clock = 1000 / float(self.actionsPerMillisecond)
        description[0]['count'] = runtime
        description[0]['clock'] = clock
        description[0]['InitDio'] = self.lastDigitalVal
        description[0]['nDigital'] = len(digitals)
        description['nAnalog'] = [len(a) for a in analogs]

        return description.tostring(), digitals, analogs
            

    ## Given a target position for the specified axis, generate an 
    # appropriate value for the DSP's analog system.
    def convertMicronsToADUs(self, aline, position):
        return long(position / self.alineToUnitsPerADU[aline])


    ## Debugging function: set the digital output for the DSP.
    def setDigital(self, value):
        self.connection.WriteDigital(value)


    ## Debugging function: set the analog voltage output for one of the DSP's
    # analog lines.
    def setAnalogVoltage(self, aline, voltage):
        # Convert volts -> ADUs
        adus = int(voltage * 6553.6)
        self.connection.MoveAbsoluteADU(aline, adus)


    ## Debugging function: plot the DSP profile we last used.
    def plotProfile(self):
        if not self.prevProfileSettings:
            return
        digitals = self.prevProfileSettings[1]
        analogs = self.prevProfileSettings[2]

        # Determine the X (time) axis
        start = min([a[0][0] for a in analogs])
        start = min(start, digitals[0,0])
        end = max([a[-1][0] for a in analogs])
        end = max(end, digitals[-1, 0])

        # Determine the Y (voltage) axis. Voltage is arbitrary for digital
        # values -- they're either on or off, but we want analogs to use the
        # full viewing area.
        minVoltage = None
        maxVoltage = None
        for axis, analog in enumerate(analogs):
            for time, val in analog:
                converted = val / 6553.60 # Convert ADUs -> volts
                if minVoltage is None or minVoltage > converted:
                    minVoltage = converted
                if maxVoltage is None or maxVoltage < converted:
                    maxVoltage = converted
        # Ensure some vaguely sane values
        if minVoltage is None:
            minVoltage = 0
        if maxVoltage is None or maxVoltage == minVoltage:
            maxVoltage = minVoltage + 1

        figure = matplotlib.figure.Figure((6, 4),
                dpi = 100, facecolor = (1, 1, 1))
        axes = figure.add_subplot(1, 1, 1)
        axes.set_axis_bgcolor('white')
        axes.set_title('DSP profile plot')
        axes.set_ylabel('Volts')
        axes.set_xlabel('Time (tenths of ms)')
        axes.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(25))

        lines = []
        labels = []
        colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']
        colorIndex = 0
        for aline, analog in enumerate(analogs):
            if numpy.any(analog) != 0:
                xVals = [a[0] for a in analog]
                yVals = [a[1] / 6553.60 for a in analog]
                lines.append(axes.plot(xVals, yVals, colors[colorIndex]))
                colorIndex += 1
                name = 'Line %d' % aline
                labels.append(name)

        # Currently-active handlers at this point
        activeNames = set()
        # Maps handler names to lists of (time, isActive) pairs
        nameToVals = {}
        for time, pattern in digitals:
            for handler, line in self.handlerToDigitalLine.iteritems():
                matches = line & pattern
                if matches and handler.name not in activeNames:
                    # We trigger this handler here
                    activeNames.add(handler.name)
                    if handler.name not in nameToVals:
                        # Everyone starts at 0.
                        nameToVals[handler.name] = [(start, 0)]
                    nameToVals[handler.name].append((time - .00001, 0))
                    nameToVals[handler.name].append((time, 1))
                elif not matches and handler.name in activeNames:
                    # We deactivate this handler here.
                    activeNames.remove(handler.name)
                    nameToVals[handler.name].append((time, 1))
                    nameToVals[handler.name].append((time + .00001, 0))

        for i, name in enumerate(sorted(nameToVals.keys())):
            scale = float(i + 1) / len(nameToVals.keys()) / 2
            xVals = []
            yVals = []
            for pair in nameToVals[name]:
                xVals.append(pair[0])
                scaledVal = minVoltage + pair[1] * scale * (maxVoltage - minVoltage)
                yVals.append(scaledVal)
            color = colors[colorIndex % len(colors)]
            colorIndex += 1
            lines.append(axes.plot(xVals, yVals, color))
            labels.append(name)

        figure.legend(lines, labels, loc = 'upper left')
        frame = wx.Frame(None, title = 'DSP Profile Plot')
        canvas = matplotlib.backends.backend_wxagg.FigureCanvasWxAgg(
                frame, -1, figure)
        canvas.draw()
        frame.Show()


    ## Debugging function: advance the SLM.
    def advanceSLM(self, count = 1):
        handler = depot.getHandlerWithName('SI SLM')
        line = self.handlerToDigitalLine[handler]
        for i in xrange(count):
            self.setDigital(line)
            self.setDigital(0)
            time.sleep(.1)
                    

    ## Debugging function: load and execute a profile.
    def runProfile(self, digitals, analogs, numReps = 1, baseDigital = 0):
        description = numpy.rec.array(None,
                formats = "u4, f4, u4, u4, 4u4",
                names = ('count', 'clock', 'InitDio', 'nDigital', 'nAnalog'),
                aligned = True, shape = 1)
        # Only doing the max of the digitals or the Z analog piezo.
        runtime = max(max(digitals[:,0]), max(analogs[1][:,0]))
        clock = 1000 / float(self.actionsPerMillisecond)
        description[0]['count'] = runtime
        description[0]['clock'] = clock
        description[0]['InitDio'] = baseDigital
        description[0]['nDigital'] = len(digitals)
        description['nAnalog'] = [len(a) for a in analogs]
        profileStr = description.tostring()

        self.connection.profileSet(profileStr, digitals, *analogs)
        self.connection.DownloadProfile()
        self.connection.InitProfile(numReps)
        events.executeAndWaitFor("DSP done", self.connection.trigCollect)
            

    def registerAnalogueDevice(self, axis, group, line, startup, sensitivity):
        line = int(line)
        # Generate a handler for the line.
        handler = handlers.genericPositioner.GenericPositionerHandler(
            axis, group, True, 
            {'moveAbsolute': lambda handler, pos: self.setAnalogVoltage(line, pos),})
        # Update mappings.
        self.handlerToAnalogLine.update({handler:line})
        self.alineToUnitsPerADU.update({line:sensitivity * 10.0 / 2**16 })
        self.startupAnalogPositions[line] = startup
        self.handlers.add(handler)
        return handler


## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class DSPOutputWindow(wx.Frame):
    def __init__(self, dsp, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## DSPDevice instance.
        self.dsp = dsp
        # Contains all widgets.
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 8, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        # Set up the digital lineout buttons.
        for line in xrange(16):
            lineVal = 1 << line
            # Check if this line is officially hooked up.
            label = str(line)
            for handler, altLine in self.dsp.handlerToDigitalLine.iteritems():
                if altLine & lineVal:
                    label = handler.name
                    break
            button = gui.toggleButton.ToggleButton(
                    parent = panel, label = label,
                    activateAction = self.toggle,
                    deactivateAction = self.toggle,
                    size = (140, 80))
            buttonSizer.Add(button, 1, wx.EXPAND)
            self.buttonToLine[button] = lineVal
        mainSizer.Add(buttonSizer)

        # Set up the analog voltage inputs.
        voltageSizer = wx.BoxSizer(wx.HORIZONTAL)
        for axis in xrange(4):
            voltageSizer.Add(wx.StaticText(panel, -1, "Voltage %d:" % axis))
            control = wx.TextCtrl(panel, -1, size = (60, -1),
                    style = wx.TE_PROCESS_ENTER)
            control.Bind(wx.EVT_TEXT_ENTER,
                    lambda event, axis = axis, control = control: self.setVoltage(axis, control))
            voltageSizer.Add(control, 0, wx.RIGHT, 20)
        mainSizer.Add(voltageSizer)
        
        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())


    ## One of our buttons was clicked; update the DSP's output.
    def toggle(self):
        output = 0
        for button, line in self.buttonToLine.iteritems():
            if button.getIsActive():
                output += line
        self.dsp.connection.WriteDigital(output)


    ## The user input text for one of the voltage controls; set the voltage.
    def setVoltage(self, axis, control):
        val = float(control.GetValue())
        self.dsp.setAnalogVoltage(axis, val)



## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
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
    _windowInstance = DSPOutputWindow(_deviceInstance, parent=wx.GetApp().GetTopWindow())
    _windowInstance.Show()
    

import threading
class BitToggler():
    def __init__(self):
        self.thread = None
        self.run = None
        self.offsets = []
        self.lock = threading.Lock()

    
    def addBit(self, offset):
        with self.lock:
            if not offset in self.offsets:
                self.offsets.append(offset)


    def removeBit(self, offset):
        with self.lock:
            if offset in self.offsets:
                self.offsets.remove(offset)


    def start(self, t0, t1):
        with self.lock:
            if self.thread:
                if self.thread.isAlive():
                    self.stop()
        self.run = True
        self.thread = threading.Thread(target=self.toggleBits, args=(t0, t1))
        self.thread.daemon = True
        self.thread.start()


    def stop(self):
        self.run = False
        if self.thread:
            self.thread.join()


    def toggleBits(self, t0, t1):
        global _deviceInstance
        d = _deviceInstance
        while(self.run):
            state = d.connection.ReadDigital()
            bits = 0
            with self.lock:
                for offset in self.offsets:
                    bits |= (1 << offset)
            d.connection.WriteDigital(state ^ bits)
            time.sleep(t0)
            state = d.connection.ReadDigital()
            d.connection.WriteDigital(state ^ bits)
            time.sleep(t1)
