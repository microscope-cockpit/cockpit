## This module handles interacting with the National Instruments cRIO-9068 that sends the digital and
# analog signals that control our light sources, cameras, and piezos. In 
# particular, it effectively is solely responsible for running our experiments.
# As such it's a fairly complex module. 
# 
# A few helpful features that need to be accessed from the commandline:
# 1) A window that lets you directly control the digital and analog outputs
#    of the FPGA.
# >>> import devices.fpga as FPGA
# >>> FPGA.makeOutputWindow()
#
# 2) Create a plot describing the actions that the NI-FPGA set up in the most
#    recent experiment profile.
# >>> import devices.fpga as FPGA
# >>> FPGA._deviceInstance.plotProfile()
#
# 3) Manually advance the SLM forwards some number of steps; useful for when
#    it has gotten offset and is no longer "resting" on the first pattern.
# >>> import devices.fpga as FPGA
# >>> FPGA._deviceInstance.advanceSLM(numSteps)
# (where numSteps is an integer, the number of times to advance it).

## TODO: Change config files.


import decimal
import matplotlib
from string import rjust
from _elementtree import Element
from __builtin__ import str
import json
matplotlib.use('WXAgg')
import matplotlib.backends.backend_wxagg
import matplotlib.figure
import numpy
# import Pyro4: In principle not used for the FPGA
import socket
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
CLASS_NAME = 'NIcRIO'
COCKPIT_AXES = {'x': 0, 'y': 1, 'z': 2, 'SI angle': -1}
CONFIG_NAME = 'nicrio9068'

class NIcRIO(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        if not self.isActive:
            return
        ## IP address of the NIcRIO RT-computer.
        self.ipAddress = config.get('nicrio9068', 'ipAddress')
        ## Port to use to send data to the NIcRIO RT-computer. Used in TCP
        self.sendPort = int(config.get('nicrio9068', 'sendPort'))
        self.receivePort = int(config.get('nicrio9068', 'receivePort'))
        self.port = [self.sendPort, self.receivePort]
        ## Create connection to the NIcRIO RT-computer
        self.connection = Connection(self.ipAddress, self.port)
        # TODO: call destructor 
        ## Set of all handlers we control.
        self.handlers = set()
        ## Where we believe the stage piezos to be.
        self.curPosition = {}
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
        # Changed to microsecond resolution. This fits better with the timed loops of the cRIO.
        self.actionsPerMillisecond = 1000
        ## Conversion factor between microns and the units the cRIO C-module NI-9269
        # uses. The MI-9269 has a 16-bit DAC (so 65536 ADUs (analog-digital units)
        # representing -10 to +10 volts).
        ##HACK retarderVoltages
        self.retarderVoltages = [0,1,2,3]
        self.alineToUnitsPerADU = {}
        self.axisMapper = {}
        VperADU = 20.0 / 2**16
        for key, aout in AOUTS.iteritems():
            self.alineToUnitsPerADU.update({\
                aout['aline']: aout['sensitivity'] * VperADU, })
            ## Maps Cockpit axes (0: X, 1: Y, 2: Z) to FPGA analog lines
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

    #TODO: Initialize socket connection: Test socket connection, reboot FPGA
    
    @util.threads.locked
    def initialize(self):
        '''
        Connect to ni's RT-host computer.
        '''
        connection = Connection(self.ipAddress, self.port)
        self.connection.abort()
        
    
    def performSubscriptions(self):
        '''
        We care when cameras are enabled, since we control some of them 
        via external trigger. There are also some light sources that we don't
        control directly that we need to know about.
        '''
        events.subscribe('camera enable', self.toggleCamera)
        events.subscribe('light source enable', self.toggleLightHandler)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)

    
    def makeInitialPublications(self):
        '''
        As a side-effect of setting our initial positions, we will also
        publish them. We want the Z piezo to be in the middle of its range
        of motion.
        '''
        self.moveRetarderAbsolute(None, 0)


    def onAbort(self):
        '''
        User clicked the abort button.
        '''
        self.connection.abort()
        events.publish('NI-FPGA done')


    @util.threads.locked
    def finalizeInitialization(self):
        #Unnecessary for the NI-FPGA
#         # Tell the remote DSP computer how to talk to us.
#         server = depot.getHandlersOfType(depot.SERVER)[0]
#         uri = server.register(self.receiveData)
#         self.connection.receiveClient(uri)
        # Get all the other devices we can control, and add them to our
        # digital lines.
        for name, line in self.nameToDigitalLine.iteritems():
            handler = depot.getHandlerWithName(name)
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
                        # TODO: What is meant by this? The DSP doesn't have modifiable soft motion safeties.
                        'setSafety': lambda *args: None},
                    COCKPIT_AXES[aout['cockpit_axis']], 
                    aout['deltas'],
                    aout['default_delta'],
                    aout['hard_limits'])
                self.handlerToAnalogLine[handler] = int(aout['aline'])#COCKPIT_AXES[aout['cockpit_axis']]
                result.append(handler)
                self.curPosition.update({COCKPIT_AXES[aout['cockpit_axis']]: 0})
                self.startupAnalogPositions[aout['aline']] = aout.get('startup_value')


            if aout['cockpit_axis'].lower() == 'si angle':
                # Variable retarder.
                self.retarderHandler = handlers.genericPositioner.GenericPositionerHandler(
                    "SI angle", "structured illumination", True, 
                    {'moveAbsolute': self.moveRetarderAbsolute, 
                    'moveRelative': self.moveRetarderRelative,
                    'getPosition': self.getRetarderPos, 
                    'getMovementTime': self.getRetarderMovementTime})
                result.append(self.retarderHandler)
                self.handlerToAnalogLine[self.retarderHandler] = aout['aline']

        for name in self.otherTriggers:
            handler = handlers.genericHandler.GenericHandler(
                name, 'other triggers', True)
            self.handlerToDigitalLine[handler] = self.nameToDigitalLine[name]
            result.append(handler)

        result.append(handlers.imager.ImagerHandler(
            "NI-FPGA imager", "imager",
            {'takeImage': self.takeImage}))

        result.append(handlers.executor.ExecutorHandler(
            "NI-FPGA experiment executor", "executor",
            {'examineActions': lambda *args: None, 
                'getNumRunnableLines': self.getNumRunnableLines, 
                'executeTable': self.executeTable}))

        self.handlers = set(result)
        return result


    ## Receive data from the RT-host computer.
    def receiveData(self, action, *args):
        if action == 'NI-FPGA done':
            print "NI-FPGA done"
            events.publish("NI-FPGA done")

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


    def toggleCamera(self, camera, isEnabled):
        '''
        Enable/disable a specific camera.
        '''
        if not isEnabled and camera.name in self.activeCameras:
            self.activeCameras.remove(camera.name)
        else:
            self.activeCameras.add(camera.name)


    def publishPiezoPosition(self, axis):
        '''
        Report the new position of a piezo.
        '''
        events.publish('stage mover', '%d piezo' % axis, 
                axis, self.curPosition[axis])


    ## Move a stage piezo to a given position.
    def movePiezoAbsolute(self, axis, pos):
        self.curPosition.update({axis: pos})
        # Convert from microns to ADUs.
        aline = self.axisMapper[axis]
        aduPos = self.convertMicronsToADUs(aline, pos)
        # TODO: sensitivity
        self.connection.writeAnalogueADU(aline, aduPos)
        self.publishPiezoPosition(axis)
        # Assume piezo movements are instantaneous; 
        # TODO: we could establish a verification through the FPGA eg: connection.MoveAbsolute does not return until done
        events.publish('stage stopped', '%d piezo' % axis)


    ## Move the stage piezo by a given delta.

    def movePiezoRelative(self, axis, delta):
        self.movePiezoAbsolute(axis, self.curPosition[axis] + delta)

    ## Get the current piezo position.
    def getPiezoPos(self, axis):
        return self.curPosition[axis]


    def getPiezoMovementTime(self, axis, start, end):
        '''
        Get the amount of time it would take the piezo to move from the 
        initial position to the final position, as well
        as the amount of time needed to stabilize after that point, 
        both in milliseconds. These numbers are both somewhat arbitrary;
        we just say it takes 1ms per micron to stabilize and .1ms to move.
        '''
        distance = abs(start - end)
        return (decimal.Decimal('.1'), decimal.Decimal(distance * 1000))


    def setSLMPattern(self, name, position):
        '''
        Set the SLM's position to a specific value. 
        For now, do nothing; the only way we can change the SLM position is by 
        sending triggers so we have no absolute positioning.
        '''
        pass


    def moveSLMPatternBy(self, name, delta):
        '''
        Adjust the SLM's position by the specified offset. Again, do nothing.
        '''
        pass


    def getCurSLMPattern(self, name):
        '''
        Get the current SLM position, either angle or phase depending on the 
        caller. We have no idea, really.
        '''
        return 0


    def getSLMStabilizationTime(self, name, prevPos, curPos):
        '''
        Get the time to move to a new SLM position, and the stabilization time, 
        in milliseconds. Note we assume that this requires only one triggering
        of the SLM.
        '''
        return (1, 30000)


    def moveRetarderAbsolute(self, name, pos):
        '''
        Move the variable retarder to the specified voltage.
        '''
        self.curRetarderVoltage = pos
        handler = depot.getHandlerWithName('SI angle')
        aline = self.handlerToAnalogLine[handler]
        # Convert from volts to ADUs.
        # TODO: add volts to ADUs in config files
        self.connection.writeAnalogueADU(aline, int(pos * 3276.8))


    def moveRetarderRelative(self, name, delta):
        '''
        Move the variable retarder by the specified voltage offset.
        '''
        self.moveRetarderAbsolute(self.curRetarderVoltage + delta)


    ## Get the current variable retarder voltage.
    def getRetarderPos(self, name):
        return self.curRetarderVoltage


    ## Get the time needed for the variable retarder to move to a new value.
    def getRetarderMovementTime(self, name, start, end):
        return (1, 1000)

    ## Take an image with the current light sources and active cameras.
    @util.threads.locked
    def takeImage(self):
        cameraMask = 0
        lightTimePairs = []
        maxTime = 0
        for handler, line in self.handlerToDigitalLine.iteritems():
            if handler.name in self.activeLights:
                maxTime = max(maxTime, handler.getExposureTime())
                exposureTime = handler.getExposureTime()
                lightTimePairs.append((line, exposureTime))
                maxTime = max(maxTime, exposureTime)
        for name, line in self.nameToDigitalLine.iteritems():
            if name in self.activeCameras:
                cameraMask += line
                handler = depot.getHandlerWithName(name)
                handler.setExposureTime(maxTime)
        self.connection.takeImage(cameraMask, lightTimePairs)


    def onPrepareForExperiment(self, *args):
        '''
        Prepare to run an experiment: cache our current piezo positions so
        we can restore them afterwards. Set our remembered output values so we
        have the correct baselines for each subset of the experiment, and set
        our values for before the experiment starts, so they can be restored
        at the end.
        '''
        self.preExperimentPosition = self.curPosition.copy()
        self.lastDigitalVal = 0
        self.lastAnalogPositions = [0] * 4


    ## Cleanup after an experiment completes: restore our cached position.
    def cleanupAfterExperiment(self, *args):
        for axis, position in self.preExperimentPosition.iteritems():
            self.movePiezoAbsolute(axis, position)


    def getNumRunnableLines(self, name, table, index):
        '''
        Get the number of actions from the provided table that we are
        capable of executing.
        '''
        return 1000
        # TODO: replace thsi method by a more sofisticated setup as the FPGA may
        # control repetitiions and the duration
#         count = 0
#         for time, handler, parameter in table[index:]:
#             # Check for analog and digital devices we control.
#             if (handler not in self.handlers and 
#                     handler.name not in self.nameToDigitalLine):
#                 # Found a device we don't control.
#                 break
#             count += 1
#         return count


    def executeTable(self, name, table, startIndex, stopIndex, numReps, repDuration):
        '''
        Actually execute the events in an experiment ActionTable, starting at
        startIndex and proceeding up to but not through stopIndex.
        # Convert the desired portion of the table into a "profile" for
        # the FPGA.
        '''
       
        profileStr, digitals, analogs = self.generateProfile(table[startIndex:stopIndex], repDuration)
        # Update our positioning values in case we have to make a new profile
        # in this same experiment. The analog values are a bit tricky, since
        # they're deltas from the values we used to create the profile.
        ## Not true for the FPGA
                
        self.lastDigitalVal = digitals[-1, 1]
        for aline in xrange(4):
            self.lastAnalogPositions[aline] = analogs[aline][-1][1] #  + self.lastAnalogPositions[aline]

        # Apologies for the messiness here; basically we're checking if any
        # aspect of the experiment profile has changed compared to the last
        # experiment we ran, if any. If there are differences, then we must
        # upload the new profile; otherwise we can skip that step.
        if (self.prevProfileSettings is None or
                profileStr != self.prevProfileSettings[0] or
                numpy.any(digitals != self.prevProfileSettings[1]) or
                sum([numpy.any(analogs[i] != self.prevProfileSettings[2][i]) for i in xrange(4)])):
            # We can't just re-use the already-loaded profile.
            self.connection.sendTables(digitalsTable = digitals, analogueTables = analogs)
            self.prevProfileSettings = (profileStr, digitals, analogs)
            
        events.publish('update status light', 'device waiting',
                'Waiting for\nFPGA to finish', (255, 255, 0))
        # InitProfile will declare the current analog positions as a "basis"
        # and do all actions as offsets from those bases, so we need to
        # ensure that the variable retarder is zeroed out first.
        # TODO: again verify if this is true for the FPGA
        retarderLine = self.handlerToAnalogLine[self.retarderHandler]
        self.setAnalogVoltage(retarderLine, 0)

        self.connection.initProfile(numReps, repDuration)
        events.executeAndWaitFor("NI-FPGA done", self.connection.triggerExperiment)

        events.publish('experiment execution')
        return


    ## Clean up after experiment is done.
    def cleanupPiezo(self, axis, isCleanupFinal):
        if isCleanupFinal:
            # The DSP may complain about still being in collection mode
            # even though it's told us it's done; wait a bit.
            time.sleep(.25)
            position = self.connection.readAnalogue(self.axisMapper[axis])
            self.curPosition.update({axis: position})
            self.publishPiezoPosition(axis)
            # Manually force all digital lines to 0, because for some reason the
            # DSP isn't doing this on its own, even though our experiments end
            # with an all-zeros entry.
            self.connection.writeDigitals(0)
            # Likewise, force the retarder back to 0.
            retarderLine = self.handlerToAnalogLine[self.retarderHandler]
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
        # TODO: whay do do this. The FPGA will only change
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
            elif handler in self.handlerToAnalogLine:
                # Analog lines step to the next position. 
                # HACK: the variable retarder shows up here too, and for it
                # we set specific voltage values depending on position.
                aline = self.handlerToAnalogLine[handler]
                value = 0
                if handler is self.retarderHandler:
                    value = int(self.retarderVoltages[action] * 3276.8)
                else:
                    value = self.convertMicronsToADUs(aline, action)
                # If we're in the
                # middle of an experiment, then these values need to be
                # re-baselined based on where we started from, since when the
                # DSP treats all analog positions as offsets of where it was
                # when it started executing the profile.
                ## not needed for teh FPGA
                # value -= self.lastAnalogPositions[aline]
                if aline not in alineToAnalogs:
                    alineToAnalogs[aline] = []
                alineToAnalogs[aline].append((time - baseTime, value))
            else:
                raise RuntimeError("Unhandled handler when generating FPGA profile: %s" % handler.name)

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
        ## Not necessary in FPGA
#         lastAnalogTime = max([a[-1, 0] for a in analogs])
#         if lastAnalogTime >= digitals[-1, 0]:
#             # Create a new array for the digital entries.
#             temp = numpy.ones((digitals.shape[0] + 1, 2), dtype = digitals.dtype)
#             # Fill in the old values
#             temp[:-1] = digitals
#             # Create a dummy action.
#             temp[-1] = [lastAnalogTime + 1, curDigitalValue]
#             digitals = temp

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
    # appropriate value for the NI-FPGA's analog system.
    def convertMicronsToADUs(self, aline, position):
        return long(position / self.alineToUnitsPerADU[aline])


    
    def setDigital(self, value):
        '''
        Debugging function: set the digital output for the NI-FPGA.
        '''
        self.connection.writeDigitals(value)


    
    # TODO: integrate this function into the configuration files
    def setAnalogVoltage(self, aline, voltage):
        '''
        Debugging function: set the analog voltage output for one of the NI-FPGA's
        analog lines.
        '''
        # Convert volts -> ADUs
        adus = int(voltage * 3276.8)
        ## TODO: sensitivity
        self.connection.writeAnalogueADU(aline, adus)


    ## Debugging function: plot the NI-FPGA profile we last used.
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
                #TODO: integrate this conversion into the config files
                converted = val / 3276.80 # Convert ADUs -> volts
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
        axes.set_title('NI-FPGA profile plot')
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
                # TODO: integrate this conversion into the config files
                yVals = [a[1] / 3276.80 for a in analog]
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
        frame = wx.Frame(None, title = 'NI-FPGA Profile Plot')
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

        self.connection.initProfile(numReps)
        events.executeAndWaitFor("NI-FPGA done", self.connection.triggerExperiment)
            
            
class Connection():
    '''
    This class handles the connection with NI's RT-host computer
    '''
    def __init__(self, host, port):
        # Edit this dictionary of common commands after updating the NI RT-host setup
        # We use a number of 3characters integers to define the commands
        # Starting with 1 and 2 are sending digitals and analogues respectivelly
        # Starting with 3 are asynchronous commands (mainly abort and reset signals
        # that should operate at any moment.
        # Starting with 4 are synchronous commands that can only operate when the
        # FPGA is idle.
        self.commandDict = {'sendDigitals' : 100,
                            'sendAnalogues' : 200,
                            'abort' : 301,
                            'reInit' : 302,
                            'reInitHost' : 303,
                            'reInitFPGA' : 304,
                            'updateNrReps' : 405,
                            'sendStartStopIndexes' : 406,
                            'initProfile' : 407,
                            'triggerExperiment' : 408,
                            'flushFIFOs': 409,
                            'writeDigitals' : 410,
                            'writeAnalogue' : 411,
                            'takeImage' : 413,
                            }
        self.errorCodes = {'0' : None,
                           '1' : 'Could not create socket',
                           '2' : 'Could not create socket connection',
                           '3' : 'Send error'}
        self.host = host
        self.port = port # port is a tuple with two values
        self.sendSocket = self.createSendSocket(self.host, self.port[0])
        self.receiveSocket = self.createReceiveSocket('', self.port[1]) #TODO: must move thsi IP to config file


#        self.fn = fn
#        self.startCollectThread()
#        self.reInit()
#        self.clientConnection = None
#        self.MoveAbsolute(0, 10)
#        self.WriteShutter(255)

    def createSendSocket(self, host, port):
        '''
        Creates a TCP socket meant to send commands to the RT-host
        
        Returns the connected socket
        '''
        try:
            # Create an AF_INET, STREAM socket (TCP)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error, msg:
            print 'Failed to create socket. Error code: ' + str(msg[0]) + ' , Error message : ' + msg[1]
            return (1, '1')
        
        try:
            # Connect to remote server
            s.connect((host , port))
        except socket.error, msg:
            print 'Failed to establish connection. Error code:' + str(msg[0]) + ' , Error message : ' + msg[1]
            return (1, '2')
        
        return s


    def createReceiveSocket(self, host, port):
        '''
        Creates a UDP socket meant to receive status information
        form the RT-host
        
        returns the bound socket
        '''
        # TODO: define host to replace symbolic link ''
        
        try:
            # Create an AF_INET, Datagram socket (UDP)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error, msg:
            print 'Failed to create socket. Error code: ' + str(msg[0]) + ' , Error message : ' + msg[1]
        
        try:
            # Bind Socket to local host and port
            s.bind((host , port))
        except socket.error, msg:
            print 'Failed to bind address. Error code:' + str(msg[0]) + ' , Error message : ' + msg[1]
        
        return s

        
    
    def writeReply(self):
        '''
        For debugging
        '''
        pass
    
    
    def runCommand(self, command, args = [], msgLength = 20):
        '''
        This method sends to the RT-host a Json command message in the following way
        - three numbers representing the command
        - if there are arguments to send:
            - the length of the messages to follow = msglength
            - the amount of messages to follow
        - receives acknowledgement of reception receiving an error code
        
        command is a 3 digits string obtained from commandDict
        
        args is a list of strings containing the arguments associated.
                
        Return a tuple where first element is 0 if success and 1 if error.
        Second element is error code.
        '''
        # Transform args into a list of strings of msgLength chars
        sendArgs = []
        for arg in args:
            if type(arg) == str and len(arg) <= msgLength:
                sendArgs.append(arg.rjust(msgLength, '0'))
            elif type(arg) == int and len(str(arg)) <= msgLength:
                sendArgs.append(str(arg).rjust(msgLength, '0'))
            else:
                try:
                    sendArgs.append(str(arg).rjust(msgLength, '0'))
                except:
                    print('Cannot send arguments to the executing device')
                    
        # Create a dictionary to be flattened and sent as json string
        
        messageCluster = {'Command': command,
                          'Message Length': msgLength,
                          'Number of Messages': len(sendArgs)
                          }
        
        try:
            ## Send the actual command
            self.sendSocket.send(json.dumps(messageCluster))
            self.sendSocket.send('\r\n')
            print('Sent command: ' + json.dumps(messageCluster))
            
            ## Send the actual messages buffer
            buf = str('').join(sendArgs)
            self.sendSocket.sendall(buf)
            print('Sent buffer:')
            print(str(buf))
            ## receive confirmation error
            errorLength = self.sendSocket.recv(4)
            error = self.sendSocket.recv(int(errorLength))
            print('error is ' + error)
            return (0, error)
        except socket.error, msg:
            #Send failed
            print 'Send failed. Error code:' + str(msg[0]) + ' , Error message : ' + msg[1]
            return (1, '3')
        
#         return (0, 0)
    
    
    def writeParameter(self, parameter, value):
        '''
        Writes parameter value to RT-host
        '''
        pass
    
    
    def readStatus(self, key = None):
        '''
        This method will listen to a UDP socket and get the status information
        of the RT-host and FPGA.
        
        This information is returned as a json string and converted to a dictionary.
        
        '''
        
        datagram = None
        
        while not datagram:
            # Receive Datagram
            print(self.receiveSocket.getsockname())
            # print(self.receiveSocket.getsockopt(level, option))
            datagram = self.receiveSocket.recvfrom(1024)
            
        
        # parse json datagram
        datagramDict = json.loads(datagram)
#         datagramList = datagram[0].split('_')
#         
#         datagramDict = {}
#         
#         for element in datagramList:
#             element = element.split('=')
#             datagramDict[element[0]] = element[1]
#             
        if key:
            return datagramDict[key]
        else:
            return datagramDict

        
    def abort(self):
        '''
        Sends abort experiment command to FPGA
        '''
        self.runCommand(self.commandDict['abort'])
        
    
    def reInit(self, unit = None):
        '''
        Restarts the RT-host and FPGA unless 'host' or 'fpga' is specified as unit
        
        Returns nothing
        '''
        if not unit:
            self.runCommand(self.commandDict['reInit'])
            
        if unit == 'host':
            self.runCommand(self.commandDict['reInitHost'])
            
        if unit == 'fpga':
            self.runCommand(self.commandDict['reInitFPGA'])

         
    def updateNReps(self, newCount, msgLength=20):
        '''
        Updates the number of repetitions to execute on the FPGA.
        
        newCount must be msgLength characters or less
        msgLength is an int indicating the length of newCount as a decimal string
        '''
        newCount = [newCount]
        
        self.runCommand(self.commandDict['updateNrReps'], newCount, msgLength)
        
        
    def sendTables(self, digitalsTable, analogueTables, msgLength = 20, digitalsBitDepth = 32, analoguesBitDepth = 16):
        '''
        Sends through TCP the digitals and analogue tables to the RT-host.
        
        Analogues lists must be ordered form 0 onward and without gaps. That is,
        (0), (0,1), (0,1,2) or (0,1,2,3). If a table is missing a dummy table must be introduced
        msgLength is an int indicating the length of every digital table element as a decimal string
        '''
        
        print('sendTables called')
        # Convert the digitals numpy table into a list of messages for the TCP
        digitalsList = []
              
        for time, value in digitalsTable:
            digitalsValue = int(numpy.binary_repr(time, 32) + numpy.binary_repr(value, 32), 2)
            digitalsList.append(digitalsValue)
                            
        # Send digitals after flushing the FPGA FIFOs
        self.runCommand(self.commandDict['flushFIFOs'])
        self.runCommand(self.commandDict['sendDigitals'], digitalsList, msgLength)
        
        # Send Analogues
        analogueChannel = 0
        for analogueTable in analogueTables:
            
            # Convert the analogues numpy table into a list of messages for the TCP
            analogueList = []
            
            for time, value in analogueTable:
                analogueValue = int(numpy.binary_repr(time, 32) + numpy.binary_repr(value, 32), 2)
                analogueList.append(analogueValue)
            
            command = str(int(self.commandDict['sendAnalogues']) + analogueChannel)
            self.runCommand(command, analogueList, msgLength)
            analogueChannel = analogueChannel + 1
            
        
    def writeIndexes(self, 
                     indexSet, 
                     digitalsStartIndex, 
                     digitalsStopIndex, 
                     analoguesStartIndexes, 
                     analoguesStopIndexes,
                     msgLength = 20):
        '''
        Writes to the FPGA the start and stop indexes of the actionTables that
        have to be run on an experiment. Actually, multiple 'indexSets' can be used
        (up to 16) to be used in combined experiments.
        
        indexSet -- the indexSet where the indexes are to be sent to. integer from 0 to 15
        digitalsStartIndex -- the start point of the digitals table. Included in
        the execution of the experiment. integer up to u32bit
        digitalsStopIndex -- the stop point of the digitals table. NOT included in
        the execution of the experiment. integer up to u32bit
        analoguesStartIndexes -- iterable containing the start points of the analogues tables.
        Included in the execution or the experiment. list or tuple of integers up to u32bit
        analoguesStopIndexes -- iterable containing the stop points of the analogues tables.
        NOT included in the execution or the experiment. list or tuple of integers up to u32bit
        msgLength is an int indicating the length of every element as a decimal string
        '''
        # TODO: Verify the value of indexSet is between 0 and 15
        # TODO: Verify that analogues lists are the same length
        
        # Merge everything in a single list to send. Note that we interlace the 
        # analogue indexes (start, stop, start, stop,...) so in the future we can 
        # put an arbitrary number. For the moment the FPGA will use 4
        sendList = [indexSet, digitalsStartIndex, digitalsStopIndex]
        
        analoguesInterleaved = [x for t in zip(analoguesStartIndexes, analoguesStopIndexes) for x in t]
        
        for index in analoguesInterleaved:
            sendList.append(index)
        
        # send indexes. 
        self.runCommand(self.commandDict['sendStartStopIndexes'], sendList, msgLength)
                   
    
    def readError(self):
        '''
        Gets error code from RT-host and FPGA
        
        Returns a tuple with the error code and the corresponding error message
        '''
        return self.getStatus('E0')       
        
    
    def isCollecting(self, collectionLine = 'Action State'):
        '''
        Returns 1 if experiment is running and 0 if idle
        '''
        return int(self.readStatus(collectionLine))
    
    
    def isAborted(self, collectionLine = 'Aborted'):
        '''
        Returns 1 if FPGA is aborted and 0 if idle
        '''
        return int(self.readStatus(collectionLine))


    def flushFIFOs(self):
        '''
        Flushes the FIFOs of the FPGA.
        '''
        self.runCommand(self.commandDict['flushFIFOs'])
    
    def writeAnalogue(self, analogueValue, analogueChannel):
        '''
        Changes an analogueChannel output to the specified analogueValue value
        
        analogueValue is taken as a calibrated value according to the sensitivity:
        
        raw value (16 or 32 bit) = analogueValue (eg V or microns) * sensitivity
        
        analogueChannel is an integer corresponding to the analogue in the FPGA 
        as specified in the config files
        '''
        pass
    
    
    def writeAnalogueADU(self, analogueChannel, analogueValueADU, msgLength=20):
        '''
        Changes an analogueChannel output to the specified analogueValue value
        
        analogueValue is taken as a raw 16 or 32bit value
        
        analogueChannel is an integer corresponding to the analogue in the FPGA 
        as specified in the config files
        msgLength is an int indicating the max length of the analogue as a decimal string

        '''
        analogue = [analogueChannel, analogueValueADU]
        
        self.runCommand(self.commandDict['writeAnalogue'], analogue, msgLength)
    
    
    def writeAnalogueDelta(self, analogueDeltaValue, analogueChannel):
        '''
        Changes an analogueChannel output to the specified analogueValue delta-value
        
        analogueDeltaValue is taken as a raw 16bit value
        
        analogueChannel is an integer corresponding to the analogue in the FPGA 
        as specified in the config files
        '''
        pass
        
    
    def readAnalogue(self, analogueLine):
        '''
        Returns the current output value of the analogue line 'analogueLine'
        
        analogueLine is an integer corresponding to the requested analogue on the FPGA
        as entered in the analogue config files.
        '''
        
        analogueLine = 'Analogue ' + str(analogueLine)
        
        return int(self.readStatus(key = analogueLine))
        
    
    def writeDigitals(self, digitalValue, msgLength=20):
        '''
        Write a specific value to the ensemble of the digitals through a 32bit
        integer digitalValue.
        msgLength is an int indicating the length of the digitalValue as a decimal string
   
        '''
        digitalValue = [digitalValue]
        self.runCommand(self.commandDict['writeDigitals'], digitalValue, msgLength)

    
    def readDigitals(self, digitalChannel = None):
        '''
        Get the value of the current Digitals outputs as a 32bit integer.
        
        If digitalChannel is specified, a 0 or 1 is returned.
        '''
        value = self.readStatus(key = 'Digitals')
        
        if digitalChannel:
            return int(value[-digitalChannel])
        
        else:
            return int(value, 2)
    
    
    def initProfile(self,numberReps, repDuration = 0, msgLength=20):
        '''
        Prepare the FPGA to run the loaded profile.
        Send a certain number of parameters:
        numberReps and a repDuration
        
        numberReps -- the number of repetitions to run
        repDuration -- the time interval between repetitions
        msgLength -- int indicating the length of numberReps and repDuration as decimal strings

        '''
        self.runCommand(self.commandDict['initProfile'], [numberReps, repDuration], msgLength)

        
    def getframedata(self):
        '''
        Get the current frame
        '''
        pass
    
    
    def triggerExperiment(self):
        '''
        Trigger the execution of an experiment.
        '''
        self.runCommand(self.commandDict['triggerExperiment'])
        
        
    def takeImage(self, cameras, lightTimePairs, actionsPerMillisecond=1000, digitalsBitDepth = 32, msgLength=20):
        '''
        Performs a snap with the selected cameras and light-time pairs
        
        Generates a list of times and digitals that is sent to the FPGA to be run
        
        Expose all lights at the start, then drop them out
        as their exposure times come to an end.
        '''
        
        if lightTimePairs:
            # transform the times in FPGA time units
            lightTimePairs = [(light, int(time * actionsPerMillisecond)) for (light, time) in lightTimePairs]
            
            # Sort so that the longest exposure time comes last.
            lightTimePairs.sort(key = lambda a: a[1])
            
            # the first timepoint: all cameras and lights are turned on and time is 0
            timingList = [(cameras + sum([p[0] for p in lightTimePairs]), 0)]
            
            # For similar exposure times, we just send the digitals values that turn off
            # all the lights
            for light, time in lightTimePairs:
                if time == timingList[-1][1]:
                    timingList[-1] = (timingList[-1][0] - light, time)
                else:
                    timingList.append((timingList[-1][0] - light, time))
                    
            # In the last time point also the cameras should be turned off
            timingList[-1] = (timingList[-1][0] - cameras, timingList[-1][1])
            
            # Add a 0 at the end will stop the execution of the list    
            timingList.append((0, 0))

            
            lightTimePairs = timingList
            
            sendList = []
            
            for light, time in lightTimePairs:
                # binarize and concatenate time and digital value
                value = numpy.binary_repr(time, 32) + numpy.binary_repr(light, digitalsBitDepth)
                value = int(value, 2)
                sendList.append(value)
                
            print(sendList)
            self.runCommand(self.commandDict['takeImage'], sendList, msgLength)
            



# 
#     def getframedata(self):
#         numframe = pyC67.GetFrameCount()
#         import numpy as N
#         #from numarray import records as rec
#         #fd=rec.array(formats="u4,u4,4f4",
#         #             shape=numframe,
#         #             names=('rep','step','adc'),
#         #             aligned=1)
#         #aa = na.array(sequence=fd._data, type=na.UInt8, copy=0, savespace=0, shape=numframe*6*4)
#         fd = N.recarray(numframe,
#                         formats="u4,u4,4f4",
#                         names='rep,step,adc')
#         #ProStr_aa[:] = 0
#         if numframe>0:
#             aa = N.ndarray(numframe*4*6, buffer=fd.data,dtype=N.uint8)
#             pyC67.ReturnFrameData(aa)
#         return fd
# 
#     def startCollectThread(self):
#         pyC67.mmInitMMTimer()
#         try:
#             self.collThread.doEvent.doWhat = 'quit'
#         except:
#             pass
#         self.collThread = CollectThread(self)
#         self.collThread.start()
# 


## This debugging window lets each digital lineout of the NI-FPGA be manipulated
# individually.
# TODO: change the class name and the corresponding calls



class FPGAOutputWindow(wx.Frame):
    def __init__(self, fpga, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## FPGADevice instance.
        self.fpga = fpga
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
            for handler, altLine in self.fpga.handlerToDigitalLine.iteritems():
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


    ## One of our buttons was clicked; update the NI-FPGA's output.
    def toggle(self):
        output = 0
        for button, line in self.buttonToLine.iteritems():
            if button.getIsActive():
                output += line
        self.connection.writeDigitals(output)


    ## The user input text for one of the voltage controls; set the voltage.
    def setVoltage(self, axis, control):
        val = float(control.GetValue())
        self.fpga.setAnalogVoltage(axis, val)



## Debugging function: display a FPGAOutputWindow.
def makeOutputWindow():
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    FPGAOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    
