#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.


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

import json
from time import sleep
import socket
import time
import numpy as np
from itertools import chain

from cockpit import depot, events
import cockpit.handlers.executor
import cockpit.handlers.imager
import cockpit.handlers.lightSource
import cockpit.handlers.stagePositioner
import threading
import cockpit.util.threads
import cockpit.util.connection
from cockpit.devices import executorDevices

COCKPIT_AXES = {'x': 0, 'y': 1, 'z': 2, 'SI angle': -1}
FPGA_IDLE_STATE = 3
FPGA_ABORTED_STATE = 4
FPGA_HEARTBEAT_RATE = .1  # At which rate is the FPGA sending update status signals
MASTER_IP = '10.6.19.11'


class NIcRIO(executorDevices.ExecutorDevice):
    _config_types = {
        'ipaddress': str,
        'sendport': int,
        'receiveport': int,
    }

    def __init__(self, name, config):
        super().__init__(name, config)
        # TODO: tickrate should go into a config?
        self.tickrate = 100  # Number of ticks per ms. As of the resolution of the action table.
        self.sendPort = config.get('sendport')
        self.receivePort = config.get('receiveport')
        self.port = [self.sendPort, self.receivePort]
        self._currentAnalogs = 4*[0]
        # Absolute positions prior to the start of the experiment.
        self._lastAnalogs = 4*[0]
        # Store last movement profile for debugging
        self._lastProfile = None
        self.connection = None

    @cockpit.util.threads.locked
    def initialize(self):
        """Connect to ni's RT-ipAddress computer. Overrides ExecutorDevice's initialize.
        """
        self.connection = Connection(parent=self, ipAddress=self.ipAddress, port=self.port, localIp=MASTER_IP)
        self.connection.connect()
        self.connection.Abort()

    @cockpit.util.threads.locked
    def finalizeInitialization(self):
        server = depot.getHandlersOfType(depot.SERVER)[0]
        self.receiveUri = server.register(self.receiveData)
        # for line in range(self.nrAnalogLines):
        #     self.setAnalog(line, 65536//2)

    def onPrepareForExperiment(self, *args):  # TODO: Verify here for weird z movements
        super().onPrepareForExperiment(*args)
        self._lastAnalogs = [self.connection.ReadPosition(a) for a in range(self.nrAnalogLines)]
        self._lastAnalogs = [line for line in self._currentAnalogs]
        self._lastDigital = self.connection.ReadDigital()

    def experimentDone(self):
        events.publish(events.EXECUTOR_DONE % self.name)

    def getAnalog(self, line):
        """Returns the current output value of the analog line in native units
        line is an integer corresponding to the requested analog on the FPGA
        as entered in the analog config files.
        """
        line = 'Analogue ' + str(line)
        return self.connection.status.getStatus(line)

    def setAnalog(self, line, target):
        """Set analog position in native units.

        Args:
            line: Analog line to change.
            target: target value.
        """
        return self.connection.MoveAbsolute(line, target)

    def getHandlers(self):
        """We control which light sources are active, as well as a set of stage motion piezos.
        """
        result = list()
        h = cockpit.handlers.executor.AnalogDigitalExecutorHandler(
            self.name, "executor",
            {'examineActions': lambda *args: None,
             'executeTable': self.executeTable,
             'readDigital': self.connection.ReadDigital,
             'writeDigital': self.connection.WriteDigital,
             'getAnalog': self.getAnalog,
             'setAnalog': self.setAnalog,
             'runSequence': self.runSequence,
             },
            dlines=self.nrDigitalLines, alines=self.nrAnalogLines)

        result.append(h)

        result.append(cockpit.handlers.imager.ImagerHandler(
            "%s imager" % self.name, "imager",
            {'takeImage': h.takeImage}))

        self.handlers = set(result)
        return result

    def _adaptActions(self, actions):
        """Adapt tha actions table to the cRIO. We have to:
        - convert float in ms to integer clock ticks
        - separate analogue and digital events into different lists
        - generate a structure that describes the profile
        """
        # Profiles
        analogs = [[] for x in range(self.nrAnalogLines)]  # A list of lists (one per channel) of tuples (ticks, (analog values))
        digitals = list()  # A list of tuples (ticks, digital state)
        # # Need to track time of last analog events
        # t_last_analog = None

        for t, (digital_args, analog_args) in actions:
            # Convert t to ticks as int while rounding up. The rounding is
            # necessary, otherwise e.g. 10.1 and 10.1999999... both result in 101.
            ticks = int(float(t) * self.tickrate + 0.5)

            # Digital actions - one at every time point.
            if len(digitals) == 0:
                digitals.append((ticks, digital_args))
            elif ticks == digitals[-1][0]:  # TODO: verify if we need this for the FPGA
                # Used to check for conflicts here, but that's not so trivial.
                # We need to allow several bits to change at the same time point, but
                # they may show up as multiple events in the actionTable. For now, just
                # take the most recent state.
                if digital_args != digitals[-1][1]:
                    digitals[-1] = (ticks, digital_args)
                else:
                    pass
            else:
                digitals.append((ticks, digital_args))

            # Analogue actions - only enter into profile on change.
            # NI-cRIO uses absolute values.
            for analog, analog_arg in zip(analogs, analog_args):
                if len(analog) == 0:  # analogs list is empty
                    analog.append((ticks, analog_arg))
                elif analog[-1][1] != analog_arg:
                    analog.append((ticks, analog_arg))
                else:
                    pass

        # Update records of last positions.
        self._lastDigital = digitals[-1][1]
        self._lastAnalogs = map(lambda x, y: x - (y[-1:][1:] or 0), self._lastAnalogs, analogs)

        # Convert digitals to array of uints.
        digitalsArr = np.array(digitals, dtype=np.uint32).reshape(-1, 2)
        # Convert analogs to array of uints.
        analogsArr = [np.array(a, dtype=np.uint32).reshape(-1, 2) for a in analogs]

        # Create a description dict. Will be byte-packed by server-side code.
        maxticks = max(chain([d[0] for d in digitals],
                             [a[0] for a in chain.from_iterable(analogs)]))

        description = {'count': maxticks,
                       'clock': 1000. / float(self.tickrate),
                       'InitDio': self._lastDigital,
                       'nDigital': len(digitals),
                       'nAnalog': [len(a) for a in analogs]}

        self._lastProfile = (description, digitalsArr, analogsArr)

        return [description, digitalsArr, [*analogsArr]]

    @cockpit.util.threads.locked
    def runSequence(self, sequence):
        """Runs a sequence of times-digital pairs"""
        # Convert the times into ticks
        sequence = [(int(t * self.tickrate), d) for t, d in sequence]
        self.connection.runSequence(sequence)

    @cockpit.util.threads.locked
    def takeBurst(self, frameCount=10):
        """
        Use the internal triggering of the camera to take a burst of images

        Experimental
        """
        cameraMask = 0
        lightTimePairs = list()
        maxTime = 0
        for handler, line in self.handlerToDigitalLine.items():
            if handler.name in self.activeLights:
                maxTime = max(maxTime, handler.getExposureTime())
                exposureTime = handler.getExposureTime()
                lightTimePairs.append((line, exposureTime))
                maxTime = max(maxTime, exposureTime)
        for name, line in self.nameToDigitalLine.items():
            if name in self.activeCameras:
                cameraMask += line
                handler = depot.getHandlerWithName(name)
                handler.setExposureTime(maxTime)

        sleep(5)


class Connection:
    """This class handles the connection with NI's RT-ipAddress computer."""
    def __init__(self, parent, ipAddress, port, localIp):
        self.parent = parent
        self.ipAddress = ipAddress
        self.port = port
        # Local IP address to use for communication, in the event that this
        # computer has multiple networks to choose from.
        self.localIp = localIp
        # ## Function to call when we get something from the camera.
        # self.callback = None
        self.connection = None
        # Edit this dictionary of common commands after updating the NI RT-ipAddress setup
        # We use a number of 3characters integers to define the commands
        # Starting with 1 and 2 are sending digitals and analogues respectively
        # Starting with 3 are asynchronous commands (mainly abort and reset signals
        # that should operate at any moment.
        # Starting with 4 are synchronous commands that can only operate when the
        # FPGA is idle.
        self.commandDict = {'sendDigitals': 100,
                            'sendAnalogues': 200,
                            'abort': 301,
                            'reInit': 302,
                            'reInitHost': 303,
                            'reInitFPGA': 304,
                            'updateNrReps': 405,
                            'sendStartStopIndexes': 406,
                            'initProfile': 407,
                            'triggerExperiment': 408,
                            'flushFIFOs': 409,
                            'writeDigitals': 410,
                            'writeAnalogue': 411,
                            'runSequence': 413,
                            }
        self.errorCodes = {'0': None,
                           '1': 'Could not create socket',
                           '2': 'Could not create socket connection',
                           '3': 'Send error'}
        self.status = None

    def receiveClient(self, URI):
        pass

    def connect(self, timeout=40):
        self.connection = self.createSendSocket(self.ipAddress, self.port[0], timeout)
        # server = depot.getHandlersOfType(depot.SERVER)[0]
        # Create a status instance to query the FPGA status and run it in a separate thread
        self.status = FPGAStatus(self, self.localIp, self.port[1])
        self.status.start()

    def getIsConnected(self):
        """Return whether or not our connection is active."""
        return self.connection is not None

    def disconnect(self):
        if self.connection is not None:
            server = depot.getHandlersOfType(depot.SERVER)[0]
            server.unregister(self.callback)
            try:
                self.connection.close()
            except Exception as e:
                print("Couldn't disconnect from %s: %s" % (self.parent.name, e))
            self.connection = None

    def createSendSocket(self, host, port, timeout):
        """Creates a TCP socket meant to send commands to the RT-ipAddress
        Returns the connected socket
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as msg:
            print('Failed to create socket.\n', msg)
            return 1, '1'

        try:
            s.settimeout(timeout)
            s.connect((host, port))
        except socket.error as msg:
            print('Failed to establish connection.\n', msg)
            return 1, '2'

        return s

    def writeReply(self):
        """For debugging"""
        pass

    def runCommand(self, command, args=(), msgLength=20):
        """This method sends to the RT-ipAddress a Json command message in the following way
        - three numbers representing the command
        - if there are arguments to send:
            - the length of the messages to follow = msglength
            - the amount of messages to follow
        - receives acknowledgement of reception receiving an error code

        command is a 3 digits string obtained from commandDict

        args is a list of strings containing the arguments associated.

        Return a Dictionary with the error description:
        Error Status, Error code and Error Description
        """
        # Transform args into a list of strings of msgLength chars
        sendArgs = list()
        for arg in args:
            if type(arg) is float:
                raise Exception('Arguments to send cannot be floats')
            if type(arg) == str and len(arg) <= msgLength:
                sendArgs.append(arg.rjust(msgLength, '0'))
            elif type(arg) == int and len(str(arg)) <= msgLength:
                sendArgs.append(str(arg).rjust(msgLength, '0'))
            else:
                sendArgs.append(str(arg).rjust(msgLength, '0'))

        # Create a dictionary to be flattened and sent as json string
        messageCluster = {'Command': command,
                          'Message Length': msgLength,
                          'Number of Messages': len(sendArgs)
                          }

        try:
            # Send the actual command
            self.connection.send(json.dumps(messageCluster).encode())
            self.connection.send(b'\r\n')
        except socket.error as msg:
            print('Send messageCluster failed.\n', msg)

        try:
            # Send the actual messages buffer
            buf = str('').join(sendArgs).encode()
            self.connection.sendall(buf)
        except socket.error as msg:
            print('Send buffer failed.\n', msg)

        try:
            # receive confirmation error
            # errorLength = int(self.connection.recv(4).decode())
            # if errorLength:
            try:
                datagram = self.connection.recv(1024)
                error = json.loads(datagram)
                if error['status']:
                    print(f'There has been an FPGA error: {error}')
            except:
                print('We received a TCP error when confirming command.')
                # errorLength.append(self.connection.recv(4096))
                # datagram = self.connection.recv(4096)

        except socket.error as msg:  # Send failed
            print('Receiving error.\n', msg)
        return

    def writeParameter(self, parameter, value):
        """Writes parameter value to RT-ipAddress
        """
        pass

    def waitForIdle(self):
        """Waits for the Idle status of the FPGA"""
        while self.status.getStatus('FPGA Main State') != FPGA_IDLE_STATE:
            time.sleep(0.1)

    def Abort(self):
        """Sends abort experiment command to FPGA
        """
        self.runCommand(self.commandDict['abort'])

    def reInit(self, unit=None):
        """Restarts the RT-ipAddress and FPGA unless 'ipAddress' or 'fpga' is specified as unit

        Returns nothing
        """
        if not unit:
            self.runCommand(self.commandDict['reInit'])

        if unit == 'ipAddress':
            self.runCommand(self.commandDict['reInitHost'])

        if unit == 'fpga':
            self.runCommand(self.commandDict['reInitFPGA'])

    def updateNReps(self, newCount, msgLength=20):
        """Updates the number of repetitions to execute on the FPGA.

        newCount must be msgLength characters or less
        msgLength is an int indicating the length of newCount as a decimal string
        """
        newCount = [newCount]

        self.runCommand(self.commandDict['updateNrReps'], newCount, msgLength)

    def sendTables(self, digitalsTable, analogueTables, msgLength=20, digitalsBitDepth=32, analoguesBitDepth=16):
        """Sends through TCP the digitals and analogue tables to the RT-ipAddress.

        Analogues lists must be ordered form 0 onward and without gaps. That is,
        (0), (0,1), (0,1,2) or (0,1,2,3). If a table is missing a dummy table must be introduced
        msgLength is an int indicating the length of every digital table element as a decimal string
        """
        # Convert the digitals numpy table into a list of messages for the TCP
        digitalsList = list()

        for t, value in digitalsTable:  # TODO: Change this into a more efficient code
            digitalsValue = int(np.binary_repr(t, 32) + np.binary_repr(value, 32), 2)
            digitalsList.append(digitalsValue)

        # Send digitals after flushing the FPGA FIFOs
        self.runCommand(self.commandDict['flushFIFOs'])
        self.runCommand(self.commandDict['sendDigitals'], digitalsList, msgLength)

        # Send Analogues
        analogueChannel = 0
        for analogueTable in analogueTables:

            # Convert the analogues numpy table into a list of messages for the TCP
            analogueList = list()

            for t, value in analogueTable:  # TODO: optimize this
                analogueValue = int(np.binary_repr(t, 32) + np.binary_repr(value, 32), 2)
                analogueList.append(analogueValue)

            command = int(self.commandDict['sendAnalogues']) + analogueChannel
            self.runCommand(command, analogueList, msgLength)
            analogueChannel = analogueChannel + 1

    def writeIndexes(self, indexSet, digitalsStartIndex, digitalsStopIndex, analoguesStartIndexes, analoguesStopIndexes,
                     msgLength=20):
        """Writes to the FPGA the start and stop indexes of the actionTables that
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
        """
        # TODO: Validate the value of indexSet is between 0 and 15
        # TODO: Validate that analogues lists are the same length

        # Merge everything in a single list to send. Note that we interlace the
        # analogue indexes (start, stop, start, stop,...) so in the future we can
        # put an arbitrary number.
        sendList = [indexSet, digitalsStartIndex, digitalsStopIndex]

        analoguesInterleaved = [x for t in zip(analoguesStartIndexes, analoguesStopIndexes) for x in t]

        for index in analoguesInterleaved:
            sendList.append(index)

        # send indexes.
        self.runCommand(self.commandDict['sendStartStopIndexes'], sendList, msgLength)

    def PrepareActions(self, actions, numReps):
        """Sends a actions table to the cRIO and programs the execution of a number of repetitions.
        It does not trigger the execution"""
        # We upload the tables to the cRIO
        self.sendTables(digitalsTable=actions[1], analogueTables=actions[2])

        # Now we can send the Indexes.
        # The indexes will tell the FPGA where the table starts and ends.
        # This allows for more flexibility in the future, as we can store more than
        # one experiment per table and just execute different parts of it.
        # Memory addresses on the FPGA are 0 based. We, however, use 1 based indexing so we
        # can initialize certain values on the 0 address of the FPGA, such as a safe state we can
        # securely rely on.
        digitalsStartIndex = 1
        digitalsStopIndex = len(actions[1])
        analoguesStartIndexes = [1 for x in actions[2]]
        analoguesStopIndexes = [len(x) for x in actions[2]]
        self.writeIndexes(indexSet=0,
                          digitalsStartIndex=digitalsStartIndex,
                          digitalsStopIndex=digitalsStopIndex,
                          analoguesStartIndexes=analoguesStartIndexes,
                          analoguesStopIndexes=analoguesStopIndexes,
                          msgLength=20)

        # We initialize the profile. That is tell the cRIO how many repetitions to produce and the interval.
        # TODO: Because the generic Executor is adding a last element in the table we put a 0 here. Change this
        self.initProfile(numReps=numReps, repDuration=0)

        return True

    def RunActions(self):
        self.triggerExperiment()

    def readError(self):
        """Gets error code from RT-ipAddress and FPGA

        Returns a tuple with the error code and the corresponding error message
        """
        return self.status.getStatus(['Error code', 'Error Description'])

    def isIdle(self):
        """Returns True if experiment is running and False if idle
        """
        if self.status.getStatus('Action State') == FPGA_IDLE_STATE:
            return True
        else:
            return False

    def isAborted(self):
        """Returns True if FPGA is aborted (in practice interlocked) and False if idle
        """
        if self.status.getStatus('Aborted'):
            return True
        else:
            return False

    def flushFIFOs(self):
        """Flushes the FIFOs of the FPGA.
        """
        self.runCommand(self.commandDict['flushFIFOs'])

    def ReadPosition(self, line):
        """Returns the current output value of the analog line in native units
        line is an integer corresponding to the requested analog on the FPGA
        as entered in the analog config files.
        """
        line = 'Analogue ' + str(line)
        return self.status.getStatus(line)

    def MoveAbsolute(self, analogueChannel, analogueValueADU, msgLength=20):
        """Changes an analogueChannel output to the specified analogueValue value

        analogueValue is taken as a raw 16 or 32bit value
        analogueChannel is an integer corresponding to the analogue in the FPGA as specified in the config files
        msgLength is an int indicating the max length of the analogue as a decimal string
        """
        analogue = [analogueChannel, int(analogueValueADU)]
        self.runCommand(self.commandDict['writeAnalogue'], analogue, msgLength)
        while self.ReadPosition(analogue[0]) != analogue[1]:
            time.sleep(0.01)
        return

    def writeAnalogueDelta(self, analogueDeltaValue, analogueChannel):
        """Changes an analogueChannel output to the specified analogueValue delta-value

        analogueDeltaValue is taken as a raw 16bit value
        analogueChannel is an integer corresponding to the analogue in the FPGA as specified in the config files
        """
        pass

    def WriteDigital(self, digitalValue, msgLength=20):
        """Write a specific value to the ensemble of the digitals through a 32bit
        integer digitalValue.
        msgLength is an int indicating the length of the digitalValue as a decimal string
        """
        digitalValue = [digitalValue]
        self.runCommand(self.commandDict['writeDigitals'], digitalValue, msgLength)

    def ReadDigital(self, digitalChannel=None):
        """Get the value of the current Digitals outputs as a 32bit integer.
        If digitalChannel is specified, a 0 or 1 is returned.
        """
        value = np.binary_repr(self.status.getStatus('Digitals'))

        if digitalChannel is not None:
            return int(value[-digitalChannel])
        else:
            return int(value, 2)

    def initProfile(self, numReps, repDuration=0, msgLength=20):
        """Prepare the FPGA to run the loaded profile.
        Send a certain number of parameters:
        numberReps and a repDuration

        numberReps -- the number of repetitions to run
        repDuration -- the time interval between repetitions
        msgLength -- int indicating the length of numberReps and repDuration as decimal strings
        """
        self.runCommand(self.commandDict['initProfile'], [numReps, repDuration], msgLength)

    def getframedata(self):
        """Get the current frame"""
        pass

    def triggerExperiment(self):
        """Trigger the execution of an experiment."""
        self.runCommand(self.commandDict['triggerExperiment'])

    def runSequence(self, time_digital_sequence, digitalsBitDepth=32, msgLength=20):
        """Runs a small sequence of digital outputs at determined times"""
        sendList = list()
        for t, d in time_digital_sequence:
            # binarize and concatenate time and digital value
            value = np.binary_repr(t, 32) + np.binary_repr(d, digitalsBitDepth)
            value = int(value, 2)
            sendList.append(value)

        self.runCommand(self.commandDict['runSequence'], sendList, msgLength)


class FPGAStatus(threading.Thread):
    def __init__(self, parent, host, port):
        threading.Thread.__init__(self)
        self.parent = parent
        # Create a dictionary to store the FPGA status and a lock to access it
        self.currentFPGAStatus = {}
        self.FPGAStatusLock = threading.Lock()

        self.socket = self.createReceiveSocket(host, port)

        # Create a handle to stop the thread
        self.shouldRun = True

    def createReceiveSocket(self, host, port):
        """Creates a UDP socket meant to receive status information
        form the RT-ipAddress

        returns the bound socket
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error as msg:
            print('Failed to create socket. Error code: ', msg)

        try:
            s.bind((host, port))
        except socket.error as msg:
            print('Failed to bind address.\n', msg)

        return s

    def getStatus(self, key=None):
        """Method to call from outside to get the status
        """
        if key and self.currentFPGAStatus is not None:
            try:
                return self.currentFPGAStatus[key]
            except KeyError as e:
                print(e)
        else:
            with self.FPGAStatusLock:
                return self.currentFPGAStatus

    def getFPGAStatus(self):
        """This method polls to a UDP socket and get the status information
        of the RT-ipAddress and FPGA.

        It will update the FPGAStatus dictionary.
        """
        try:
            # datagramLength = int(self.socket.recvfrom(4)[0].decode())
            datagram = self.socket.recvfrom(1024)[0]
        except:
            print('Error receiving status datagram: ', datagram)

        try:
            status = json.loads(datagram)
        except:
            print('Could not serialize status datagram: ', datagram)
            return

        return status

    def publishFPGAStatusChanges(self, newStatus):
        """FInd interesting status or status changes in the FPGA and publish them

        return the newStatus but with the status reset so not to publish multiple times
        """
        if newStatus['Event'] in ['done', 'FPGA done']:
            self.parent.parent.experimentDone()
            # events.publish(events.EXECUTOR_DONE, self.parent.parent.name)
            newStatus['Event'] = ''

        return newStatus

    def run(self):
        self.currentFPGAStatus = self.getFPGAStatus()
        update_rate = FPGA_HEARTBEAT_RATE / 2

        while self.shouldRun:
            newFPGAStatus = self.getFPGAStatus()
            # with self.FPGAStatusLock:
            if newFPGAStatus['Event'] != self.currentFPGAStatus['Event'] and \
                    newFPGAStatus['Event'] == 'done' and \
                    newFPGAStatus is not None:
                # Publish any interesting events
                self.currentFPGAStatus = self.publishFPGAStatusChanges(newStatus=newFPGAStatus)
            else:
                self.currentFPGAStatus = newFPGAStatus

            # wait for a period of half the broadcasting rate of the FPGA
            time.sleep(update_rate)
