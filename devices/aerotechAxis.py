"""Cockpit aerotechAxis

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================

This module creates a simple stage-positioning device.
"""

import depot
import device
import events
import handlers.stagePositioner

import functools
import socket
import re
from time import sleep

from config import config

CLASS_NAME = 'AerotechZStage'
CONFIG_NAME = 'aerotech'
NAME_STRING = 'aerotech mover' 
LIMITS_PAT = r"(?P<limits>\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\))"

## Characters used by the SoloistCP controller.
# CommandTerminatingCharacter
CTC = chr(10)
# CommandSuccessCharacter
CSC = chr(37)
# CommandInvalidCharacter
CIC = chr(33)
# CommandFaultCharacter
CFC = chr(35)
# CommandTimeOutCharacter
CTOC = chr(36)
# Map character to meaning
RESPONSE_CHARS = {
    CSC: 'command success',
    CIC: 'command invalid',
    CFC: 'command caused fault',
    CTOC: 'command timeout',
    }


class AerotechZStage(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        self.isActive = config.has_section(CONFIG_NAME)
        if self.isActive:
            # Enable in depot.
            self.enabled = True
            # IP address of the controller.
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')   
            # Controller port.
            self.port = config.getint(CONFIG_NAME, 'port')
			#
            try :
                limitString = config.get(CONFIG_NAME, 'softlimits')
                parsed = re.search(LIMITS_PAT, limitString)
                if not parsed:
                    # Could not parse config entry.
                    raise Exception('Bad config: PhysikInstrumentsM687 Limits.')
                    # No transform tuple
                else:    
                    lstr = parsed.groupdict()['limits']
                    self.softlimits=eval(lstr)
            except:
                print "No softlimits section setting default limits"
                self.softlimits = (-30000,7000)

			
			
            # Subscribe to abort events.
            events.subscribe('user abort', self.onAbort)
            # The cockpit axis does this stage moves along.
            self.axis = config.getint(CONFIG_NAME, 'axis')
            # Socket used to communicate with controller.
            self.socket = None
            # Last known position (microns)
            self.position = None
            # Axis acceleration (mm / s^2)
            self.acceleration = 200
            # Axis maximum speed (mm / s^2)
            self.speed = 20

    
    ## Send a command to the Aerotech SoloistCP and fetch the response.
    def command(self, cmd):
        # The terminated command string.
        cmdstr = cmd + CTC
        # A flag indicating that a retry is needed.
        retry = False

        ## Try to send the command.
        try:
            self.socket.send(cmdstr)
        except socket.error as e:
            retry = True
        except:
            raise

        ## Was there a connection error?
        if retry:
            self.openConnection()
            try:
                self.socket.send(cmdstr)
            except:
                raise

        ## Fetch and parse the response
        response = self.socket.recv(256)
        # Response status character:
        response_char = response[0]
        # Response data:
        response_data = response[1:]
        
        # Did the controlle report a problem?
        if response_char != CSC:
            raise Exception('Aerotech controller error - %s.' 
                            % RESPONSE_CHARS[response_char])
        else:
            return response_data

       
    def getHandlers(self):
        result = []
        axis = self.axis
        minVal = self.softlimits[0]
        maxVal = self.softlimits[1]
        handler = handlers.stagePositioner.PositionerHandler(
            "%d %s" % (axis, NAME_STRING), "%d stage motion" % axis, True, 
            {'moveAbsolute': self.moveAbsolute,
                'moveRelative': self.moveRelative, 
                'getPosition': self.getPosition, 
                'getMovementTime': self.getMovementTime,
                'cleanupAfterExperiment': self.cleanup,
                'setSafety': self.setSafety},
                axis, [1, 5, 10, 50, 100, 500, 1000, 5000],
                1, (minVal, maxVal), (minVal, maxVal))
        result.append(handler)
        return result
    
    
    ## Initialize the axis.
    def initialize(self):
        # Open a connection to the controller.
        self.openConnection()
        self.position = self.command('CMDPOS')
        self.speed = int(self.command('GETPARM(71)'))
        self.acceleration = int(self.command('GETPARM(72'))


    ## Publish our current position.
    def makeInitialPublications(self):
        axis = self.axis
        events.publish('stage mover', '%d %s' % (axis, NAME_STRING), axis,
                self.position)


    ## User clicked the abort button; stop moving.
    def onAbort(self):
        self.command('ABORT')
        axis = self.axis
        events.publish('stage stopped', '%d %s' % (axis, NAME_STRING))


    ## Move the stage to a given position.
    def moveAbsolute(self, axis, pos):
        self.command('ENABLE')
        self.command('MOVEABS D %f F %f'
                        % (pos / 1000.0, self.speed))
        events.publish('stage mover', '%d %s' % (axis, NAME_STRING), axis, self.position)
        # Wait until the move has finished - status bit 2 is InPosition.
        while not int(self.command('AXISSTATUS')) & (1 << 2):
            sleep(0.1)
        self.position = self.command('CMDPOS')
        events.publish('stage mover', '%d %s' % (axis, NAME_STRING), axis, self.position)
        events.publish('stage stopped', '%d mover' % axis)
        self.command ('DISABLE')


    ## Move the stage piezo by a given delta.
    def moveRelative(self, axis, delta):
        self.command('ENABLE')
        self.command('MOVEINC D %f F %f'
                        % (delta / 1000.0, self.speed))
        events.publish('stage mover', '%d %s' % (axis, NAME_STRING), axis, self.position)
        # Wait until the move has finished - status bit 2 is InPosition.
        while not int(self.command('AXISSTATUS')) & (1 << 2):
            sleep(0.1)
        self.position = self.command('CMDPOS')
        events.publish('stage mover', '%d %s' % (axis, NAME_STRING), axis, self.position)
        events.publish('stage stopped', '%d %s' % (axis, NAME_STRING))
        self.command ('DISABLE')


    ## Get the current piezo position.
    def getPosition(self, axis):
        return float(self.position)*1000.0


    ## Get the amount of time it would take the mover to move from the 
    # initial position to the final position, as well
    # as the amount of time needed to stabilize after that point, 
    # both in milliseconds. This is needed when setting up timings for 
    # experiments.
    def getMovementTime(self, axis, start, end):
        # top speed mm/s
        v = self.speed
        # acceleration mm/s**2
        a = self.acceleration
        # displacement - passed as um
        dS = abs(start - end) / 1000.0
        # acceleration / braking distance
        S_acc = 0.5 * v**2 / a
        
        # Determine time required for move, in ms.
        if dS < 2 * S_acc:
            dt = 1000 * 2 * (dS / a)**0.5
        else:
            dt = 1000 * ((dS / v) + (v / a))

        # Add a few ms to allow for any network latency (measured at < 10ms).
        dt += 10

        # The stage slows gradually to a stop so settling time is small.
        # Allow one or two servo cycles - servo rate is 1kHz.
        return (dt, 2)


    def openConnection(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.ipAddress, self.port))
        except:
            raise


    ## Set the soft motion safeties for one of the movers. Note that the 
    # PositionerHandler provides its own soft safeties on the cockpit side; 
    # this function just allows you to propagate safeties to device control
    # code, if applicable.
    def setSafety(self, axis, value, isMax):
        pass


    ## Cleanup after an experiment. For a real mover, this would probably 
    # just mean making sure we were back where we were before the experiment
    # started.
    def cleanup(self, axis, isCleanupFinal):
        self.moveAbsolute(axis, self.position)
