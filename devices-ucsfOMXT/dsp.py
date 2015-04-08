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
import delayGen
import device
import events
import gui.toggleButton
import handlers.executor
import handlers.genericHandler
import handlers.genericPositioner
import handlers.imager
import handlers.lightSource
import handlers.stagePositioner
import util.logger
import util.threads
from config import config

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
        ## Current voltage output for the variable retarder.
        self.curRetarderVoltage = 0
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
        self.nameToDigitalLine = {
                'Zyla': 1 << 0,
                'iXon1': 1 << 1,
        }
        ## Information regarding light sources we control.
        self.lightInfo = [('Ambient light', 'Ambient', 0),
                ('488 shutter', 488, 1 << 3),
                ('561 shutter', 561, 1 << 11)]

        ## Generic handler to represent the trigger for the digital delay
        # generator.
        self.delayHandler = None
        ## Generic handler to represent the trigger for the 561 AOM.
        self.aom561Handler = None
        ## Resolution of actions we can take when running experiments.
        self.actionsPerMillisecond = 10
        ## Conversion factor between microns and the units the DSP card
        # uses. The DSP has a 16-bit DAC (so 65536 ADUs (analog-digital units)
        # representing 0-10 volts).
        self.axisToMicronsPerADU = {
            # For the Lisa piezo
#            2: .00046035
            # For the PhysikInstrumente piezo
            2: 200 / 65536.0
        }
        ## Maps Cockpit axes (0: X, 1: Y, 2: Z) to DSP analog lines
        # (0: old Lisa piezo; 1: new PI piezo; 2: variable retarder)
        self.axisMapper = {2: 1, 0: 2}
        ## Voltage values for the variable retarder for each angle in an SI
        # experiment.
        self.retarderVoltages = [0.74, 0.91, 2.50]
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


    ## As a side-effect of setting our initial positions, we will also
    # publish them. We want the Z piezo to be in the middle of its range
    # of motion.
    def makeInitialPublications(self):
        self.movePiezoAbsolute(2, 100)
        self.moveRetarderAbsolute(None, 0)


    ## Add a couple of buttons to access some specific functionality: the
    # direct output control window, and the advanceSLM function.
    def makeUI(self, parent):
        panel = wx.Panel(parent)
        panelSizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, -1, "DSP Controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        panelSizer.Add(label)
        
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        button = gui.toggleButton.ToggleButton(
                label = "DSP\nTTL", parent = panel, size = (84, 50))
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: makeOutputWindow())
        buttonSizer.Add(button)

        button = gui.toggleButton.ToggleButton(
                label = "Advance SLM", parent = panel, size = (84, 50))
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: self.advanceSLM())
        buttonSizer.Add(button)

        panelSizer.Add(buttonSizer)
        panel.SetSizerAndFit(panelSizer)
        
        return panel


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
        for label, wavelength, line in self.lightInfo:
            # Set up lightsource handlers. Default to 100ms exposure time.
            handler = handlers.lightSource.LightHandler(
                label, "%s light source" % label, 
                {'setEnabled': self.toggleLight,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime}, wavelength, 100)
            self.lightToExposureTime[handler.name] = 100
            self.handlerToDigitalLine[handler] = line
            result.append(handler)

        for axis in [2]:
            # Stage motion piezo; we just have the one here.
            handler = handlers.stagePositioner.PositionerHandler(
                "%d piezo" % axis, "%d stage motion" % axis, True, 
                {'moveAbsolute': self.movePiezoAbsolute,
                    'moveRelative': self.movePiezoRelative, 
                    'getPosition': self.getPiezoPos, 
                    'getMovementTime': self.getPiezoMovementTime,
                    'cleanupAfterExperiment': self.cleanupPiezo,
                 # No modifiable soft motion safeties.
                    'setSafety': lambda *args: None},
                axis, [.01, .05, .1, .5, 1, 5, 10, 50], 2, (0, 200))
            self.handlerToAnalogAxis[handler] = axis
            result.append(handler)

        # Variable retarder.
        self.retarderHandler = handlers.genericPositioner.GenericPositionerHandler(
            "SI angle", "structured illumination", True, 
            {'moveAbsolute': self.moveRetarderAbsolute, 
                'moveRelative': self.moveRetarderRelative,
                'getPosition': self.getRetarderPos, 
                'getMovementTime': self.getRetarderMovementTime})
        result.append(self.retarderHandler)
        # HACK: axis we provide here is bogus; will be converted to the
        # proper address in generateProfile.
        # \todo Handle this better. Too hungry right now.
        self.handlerToAnalogAxis[self.retarderHandler] = 0

        # SLM handler
        if config.has_section('slm'):
            line = int(config.get('slm', 'line'))
            result.append(handlers.genericPositioner.GenericPositionerHandler(
                    "SI SLM", "structured illumination", True, 
                    {'moveAbsolute': self.setSLMPattern, 
                     'moveRelative': self.moveSLMPatternBy,
                     'getPosition': self.getCurSLMPattern, 
                     'getMovementTime': self.getSLMStabilizationTime}))
            self.handlerToDigitalLine[result[-1]] = 1 << line

        # 561 AOM handler
        self.aom561Handler = handlers.genericHandler.GenericHandler(
            "561 AOM", "561 light source", True)
        result.append(self.aom561Handler)
        self.handlerToDigitalLine[self.aom561Handler] = 1 << 12

        # Delay generator for the 488 AOM.
        self.delayHandler = handlers.genericHandler.GenericHandler(
            'Delay generator trigger', 'General light control', True)
        self.handlerToDigitalLine[self.delayHandler] = 1 << 4
        result.append(self.delayHandler)

        result.append(handlers.imager.ImagerHandler(
            "DSP imager", "imager",
            {'takeImage': self.takeImage}))
        result.append(handlers.executor.ExecutorHandler(
            "DSP experiment executor", "executor",
            {'examineActions': self.examineActions, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable}))

        self.handlers = set(result)
        return result


    ## Receive data from the DSP computer.
    def receiveData(self, *args):
        events.publish("DSP done")


    ## Enable/disable a specific light source.
    def toggleLight(self, lightName, isEnabled):
        if isEnabled:
            self.activeLights.add(lightName)
        elif lightName in self.activeLights:
            self.activeLights.remove(lightName)


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
        self.curPosition[axis] = pos
        # Convert from microns to ADUs.
        aduPos = int(pos / self.axisToMicronsPerADU[axis])
        self.connection.MoveAbsoluteADU(self.axisMapper[axis], aduPos)
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


    ## Move the variable retarder to the specified voltage.
    def moveRetarderAbsolute(self, name, pos):
        self.curRetarderVoltage = pos
        # Convert from volts to ADUs.
        # \todo Axis handled manually here.
        self.connection.MoveAbsoluteADU(2, int(pos * 6553.6))


    ## Move the variable retarder by the specified voltage offset.
    def moveRetarderRelative(self, name, delta):
        self.moveRetarderAbsolute(self.curRetarderVoltage + delta)


    ## Get the current variable retarder voltage.
    def getRetarderPos(self, name):
        return self.curRetarderVoltage


    ## Get the time needed for the variable retarder to move to a new value.
    def getRetarderMovementTime(self, name, start, end):
        return (1, 1)


    ## Take an image with the current light sources and active cameras.
    @util.threads.locked
    def takeImage(self):
        cameraMask = 0
        lightTimePairs = []
        
        # Track the max exposure time; will be used as the camera
        # exposure time.
        maxTime = 0
        for handler, line in self.handlerToDigitalLine.iteritems():
            if handler.name in self.activeLights:
                if handler.name == '488 shutter':
                    # If using the 488 light source, need to use the delay
                    # generator to manipulate the AOM that gates that light
                    # source.  Because there is an initial delay with the
                    # delay generator, need to modify the requested exposure
                    # time.
                    generator = depot.getDevice(delayGen)
                    delay = generator.getInitialDelay()
                else:
                    delay = 0
                # The DSP card can only handle integer exposure times.
                exposureTime = int(numpy.ceil(handler.getExposureTime())) + delay + 1
                maxTime = max(maxTime, exposureTime)
                # Enforce a minimum exposure time of 10ms for the shutter,
                # which gets erratic at very low exposure times. The delay
                # generator will handle fine exposure time resolution.
                lightTimePairs.append((line, max(exposureTime, 10)))
                if handler.name == '488 shutter':
                    # The delay generator needs to know how long a pulse to
                    # send.
                    generator.setExposureTime(handler.name, handler.getExposureTime())
                    # Trigger the delay generator alongside any lights.
                    # It takes a TTL pulse instead of a normal exposure signal.
                    lightTimePairs.append(
                        (self.handlerToDigitalLine[self.delayHandler], 1))
                elif handler.name == '561 shutter':
                    # Trigger the 561 AOM.  Because this goes through the
                    # DSP, use the exposure time coerced to be appropriate
                    # for the DSP.
                    lightTimePairs.append(
                        (self.handlerToDigitalLine[self.aom561Handler],
                         exposureTime))
        for name, line in self.nameToDigitalLine.iteritems():
            if name in self.activeCameras:
                cameraMask += line
                handler = depot.getHandlerWithName(name)
                handler.setExposureTime(maxTime)
        self.connection.arcl(cameraMask, lightTimePairs)


    ## Prepare for an experiment: set our remembered output values so we
    # have the correct baselines for each subset of the experiment, and set
    # our values for before the experiment starts, so they can be restored
    # at the end.
    def onPrepareForExperiment(self, *args):
        self.lastDigitalVal = 0
        self.lastAnalogPositions = [0] * 4


    ## Examine an ActionTable for validity. Replace activations of the 561
    # shutter with activations of the 561 AOM, and open the shutter at the
    # beginning and end of the experiment instead.
    def examineActions(self, name, table):
        have561 = False
        for i, (time, handler, parameter) in enumerate(table.actions):
            if handler.name == '561 shutter':
                have561 = True
                # Remove the event since it'll be replaced by triggering
                # the AOM.
                table.actions[i] = None
                table.addAction(time, self.aom561Handler, parameter)
        table.clearBadEntries()
        
        if have561:
            shutterHandler = depot.getHandlerWithName('561 shutter')
            start, end = table.getFirstAndLastActionTimes()
            table.addAction(start, shutterHandler, True)
            table.addAction(end + decimal.Decimal('.1'),
                    shutterHandler, False)
            


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
        # InitProfile will declare the current analog positions as a "basis"
        # and do all actions as offsets from those bases, so we need to
        # ensure that the variable retarder is zeroed out first.
        retarderLine = self.axisMapper[self.handlerToAnalogAxis[self.retarderHandler]]
        self.setAnalogVoltage(retarderLine, 0)

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
            # Force the analog axes to where they were at the very start of
            # the experiment.
            self.movePiezoAbsolute(2, self.curPosition[2])
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
                # HACK: the variable retarder shows up here too, and for it
                # we set specific voltage values depending on position.
                axis = self.handlerToAnalogAxis[handler]
                value = 0
                if handler is self.retarderHandler:
                    value = int(self.retarderVoltages[action] * 6553.6)
                else:
                    value = self.convertMicronsToADUs(axis, action)
                # If we're in the
                # middle of an experiment, then these values need to be
                # re-baselined based on where we started from, since when the
                # DSP treats all analog positions as offsets of where it was
                # when it started executing the profile.
                value -= self.lastAnalogPositions[self.axisMapper[axis]]
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
        return position / self.axisToMicronsPerADU[axis]


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
    
