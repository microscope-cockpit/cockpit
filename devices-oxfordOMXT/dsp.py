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
import handlers.genericPositioner
import handlers.imager
import handlers.lightSource
import handlers.stagePositioner
import util.threads
from config import config, LIGHTS, CAMERAS
CLASS_NAME = 'DSPDevice'

class DSPDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        if not config.has_section('dsp'):
            raise Exception('No dsp section found in config.')
        ## IP address of the DSP computer.
        self.ipAddress = config.get('dsp', 'ipAddress')
        ## Port to use to connect to the DSP computer.
        self.port = int(config.get('dsp', 'port'))
        ## Connection to the remote DSP computer
        self.connection = None
        ## Set of all handlers we control.
        self.handlers = set()
        ## Where we believe the stage piezos to be.
        self.curPosition = [0, 0, 0]
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
        self.handlerToAnalogAxis = {}
        ## Maps handler names to the digital lines we use to activate those
        # devices. 
        self.nameToDigitalLine = {}
        self.nameToDigitalLine.update({key: val['line'] for \
                                       key, val in LIGHTS.iteritems()})
        self.nameToDigitalLine.update({key: val['line'] for \
                                       key, val in CAMERAS.iteritems()})
        ## Resolution of actions we can take when running experiments.
        self.actionsPerMillisecond = 10
        ## Conversion factor between microns and the units the DSP card
        # uses. Manually calibrated.
        self.micronsPerADU = numpy.array(
                [5.9029E-4, 5.89606E-4, 5.88924E-4, 15.259E-4])
        ## Maps Cockpit axes (0: X, 1: Y, 2: Z) to DSP axes
        # (0: Z, 1: Y, 2: X)
#IMD 20130625 - Z steps on piezo drive the X posotion, so revervse this mapping
#        self.axisMapper = dict(zip(range(3), range(3)[::-1]))
        self.axisMapper = dict(zip(range(3), range(3)))
  
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


    ## Connect to the DSP computer.
    # Move the piezos in a bit so they're away from any motion limits.
    @util.threads.locked
    def initialize(self):
        uri = 'PYRO:pyroDSP@%s:%d' % (self.ipAddress, self.port)
        self.connection = Pyro4.Proxy(uri)
        self.connection._pyroTimeout = 3
        self.connection.Abort()
        print "dsp init"
        for i in xrange(3):
            self.movePiezoAbsolute(i, 10)


    ## We care when cameras are enabled, since we control some of them 
    # via external trigger. There are also some light sources that we don't
    # control directly that we need to know about.
    def performSubscriptions(self):
        events.subscribe('camera enable', self.toggleCamera)
        events.subscribe('light source enable', self.toggleLightHandler)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.prepareForExperiment)
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)


    ## User clicked the abort button.
    def onAbort(self):
        self.connection.Abort()


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
            self.handlerToDigitalLine[handler] = line


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
            self.handlerToDigitalLine[handler] = light['line']
            result.append(handler)
        for axis in xrange(3):
            handler = handlers.stagePositioner.PositionerHandler(
                "%d piezo" % axis, "%d stage motion" % axis, True, 
                {'moveAbsolute': self.movePiezoAbsolute,
                    'moveRelative': self.movePiezoRelative, 
                    'getPosition': self.getPiezoPos, 
                    'getMovementTime': self.getPiezoMovementTime,
                    'cleanupAfterExperiment': self.cleanupPiezo,
                 # The DSP doesn't have modifiable soft motion safeties.
                    'setSafety': lambda *args: None},
                axis, [.01, .05, .1, .5, 1], 2, (0, 30))
            self.handlerToAnalogAxis[handler] = axis
            result.append(handler)
        result.append(handlers.imager.ImagerHandler(
            "DSP imager", "imager",
            {'takeImage': self.takeImage}))
        result.append(handlers.genericPositioner.GenericPositionerHandler(
            "SI phase", "phase piezo", True,
            {'moveAbsolute': self.movePhaseAbsolute,
                'moveRelative': self.movePhaseRelative,
                'getPosition': self.getPhasePosition,
                'getMovementTime': self.getPhaseMovementTime}))
        result.append(handlers.executor.ExecutorHandler(
            "DSP experiment executor", "executor",
            {'examineActions': lambda *args: None, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable}))
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


    ## As toggleLight, but accepts a Handler instead.
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
        if isEnabled:
            self.activeCameras.add(camera.name)
        elif camera.name in self.activeCameras:
            self.activeCameras.remove(camera.name)



    ## Report the new position of a piezo.
    def publishPiezoPosition(self, axis):
        events.publish('stage mover', '%d piezo' % axis, 
                axis, self.curPosition[axis])


    ## Move the stage piezo to a given position.
    def movePiezoAbsolute(self, axis, pos):
        self.curPosition[axis] = pos
        self.connection.MoveAbsolute(self.axisMapper[axis], self.curPosition[axis])
        self.publishPiezoPosition(axis)
        # Assume piezo movements are instantaneous; we don't get notified by
        # the DSP when motion stops, anyway.
        events.publish('stage stopped', '%d piezo' % axis)


    ## Move the stage piezo by a given delta.
    def movePiezoRelative(self, axis, delta):
        self.curPosition[axis] += delta
        self.connection.MoveAbsolute(self.axisMapper[axis], self.curPosition[axis])
        self.publishPiezoPosition(axis)
        # Assume piezo movements are instantaneous; we don't get notified by
        # the DSP when motion stops, anyway.
        events.publish('stage stopped', '%d piezo' % axis)


    ## Get the current piezo position.
    def getPiezoPos(self, axis):
        return self.curPosition[axis]


    ## Get the amount of time it would take the piezo to move from the 
    # initial position to the final position, as well
    # as the amount of time needed to stabilize after that point, 
    # both in milliseconds.
    def getPiezoMovementTime(self, axis, start, end):
        return (1, 1)


    ## Move the phase piezo to the specified position.
    def movePhaseAbsolute(self, name, pos):
        pass


    ## Move the phase piezo by a given delta.
    def movePhaseRelative(self, name, delta):
        pass


    ## Get the current phase piezo position.
    def getPhasePosition(self, name):
        return None


    ## Get the amount of time it would take the phase piezo to move from the 
    # initial position to the final position, as well
    # as the amount of time needed to stabilize after that point, 
    # both in milliseconds.
    def getPhaseMovementTime(self, name, start, end):
        return (1, 20)


    ## Take an image with the current light sources and active cameras.
    @util.threads.locked
    def takeImage(self):
        cameraMask = 0
        lightTimePairs = []
        maxTime = 0
        for handler, line in self.handlerToDigitalLine.iteritems():
            if handler.name in self.activeLights:
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
    def prepareForExperiment(self, *args):
        self.preExperimentPosition = tuple(self.curPosition)
        self.lastDigitalVal = 0
        self.lastAnalogPositions = [0] * 4


    ## Cleanup after an experiment completes: restore our cached position.
    def cleanupAfterExperiment(self, *args):
        for axis, position in enumerate(self.preExperimentPosition):
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

    ## Actually execute the events in the table, starting at startIndex 
    # and proceeding up to but not through stopIndex.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        # Convert the desired portion of the table into a "profile" for
        # the DSP card.
        profileStr, digitals, analogs = self.generateProfile(table[startIndex:stopIndex], repDuration)
        # Update our positioning values in case we have to make a new profile
        # in this same experiment. The analog values are a bit tricky, since
        # they're deltas from the values we used to create the profile.
        self.lastDigitalVal = digitals[-1, 1]
        for axis in xrange(4):
            self.lastAnalogPositions[axis] = analogs[axis][-1][1] + self.lastAnalogPositions[axis]

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
            self.curPosition[axis] = position
            self.publishPiezoPosition(axis)
            # Manually force all digital lines to 0, because for some reason the
            # DSP isn't doing this on its own, even though our experiments end
            # with an all-zeros entry.
            self.connection.WriteDigital(0)
            # Likewise, force the retarder back to 0.
            retarderLine = self.axisMapper[self.handlerToAnalogAxis[self.retarderHandler]]
            self.setAnalogVoltage(retarderLine, 0)


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
        axisToAnalogs = {}
        for time, handler, action in events:
            # Do the same "Decimal -> float -> rounded int" conversion
            time = int(float(time * self.actionsPerMillisecond) + .5)
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
            elif handler in self.handlerToAnalogAxis:
                # Analog lines step to the next position.
                axis = self.handlerToAnalogAxis[handler]
                value = self.convertMicronsToADUs(axis, action)
                if axis not in axisToAnalogs:
                    axisToAnalogs[axis] = []
                axisToAnalogs[axis].append((time - baseTime, value))
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
        for axis, actions in axisToAnalogs.iteritems():
            analogs[self.axisMapper[axis]] = numpy.zeros((len(actions), 2), dtype = numpy.uint32)
            for i, (time, value) in enumerate(actions):
                analogs[self.axisMapper[axis]][i] = (time, value)

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
        for axis in xrange(4):
            runtime = max(runtime, max(analogs[axis][:, 0]))
        clock = 1000 / float(self.actionsPerMillisecond)
        description[0]['count'] = runtime
        description[0]['clock'] = clock
        description[0]['InitDio'] = self.lastDigitalVal
        description[0]['nDigital'] = len(digitals)
        description['nAnalog'] = [len(a) for a in analogs]

        return description.tostring(), digitals, analogs
            

    ## Given a target position for the specified axis, generate an 
    # appropriate value for the DSP's analog system.
    def convertMicronsToADUs(self, axis, position):
        return position / self.micronsPerADU[axis]


    ## Debugging function: set the digital output for the DSP.
    def setDigital(self, value):
        self.connection.WriteDigital(value)


    ## Debugging function: set the analog voltage output for one of the DSP's
    # analog lines.
    def setAnalogVoltage(self, axis, voltage):
        # Convert volts -> ADUs
        adus = int(voltage * 6553.6)
        self.connection.MoveAbsoluteADU(axis, adus)


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
        for axis, analog in enumerate(analogs):
            if numpy.any(analog) != 0:
                xVals = [a[0] for a in analog]
                yVals = [a[1] / 6553.60 for a in analog]
                lines.append(axes.plot(xVals, yVals, colors[colorIndex]))
                colorIndex += 1
                name = 'Axis %d' % axis
                for handler, altAxis in self.handlerToAnalogAxis.iteritems():
                    if altAxis in self.axisMapper and axis == self.axisMapper[altAxis]:
                        name = handler.name
                        break
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
        # InitProfile will declare the current analog positions as a "basis"
        # and do all actions as offsets from those bases, so we need to
        # ensure that the variable retarder is zeroed out first.
        retarderLine = self.axisMapper[self.handlerToAnalogAxis[self.retarderHandler]]
        self.setAnalogVoltage(retarderLine, 0)

        self.connection.InitProfile(numReps)
        events.executeAndWaitFor("DSP done", self.connection.trigCollect)
            


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
def makeOutputWindow():
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    DSPOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    
