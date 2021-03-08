#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
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

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


from cockpit.devices import device
from cockpit import events
import cockpit.handlers.stagePositioner
import cockpit.util.threads

import socket
import threading
import time

import cockpit.util.logger
## TODO: test with hardware.


#few commnads
# pr - position relative
# pa - position aboslute
# mm - position mode (1 -= closed loop)
# sn - units mode 0= steps, 1= counts from encoder
# dh - set home
# md - motion done? 1=finished 0= in motion
# fe - feedback error limit default = 1000
# cl - closeed loop update freq in sec min = 0.1
# ab - abort motion
# mt - move to limit (suggest index on -ve limit on all channels)
# tp? - query position.
# or - find home? not sure what this means with current stages

#Need to sort out defined positions. How do we know if the system has been homed?
# How dowes this compare to "1 or"? I have no clue!
# movement range is ~   335926 counts - need to measure distance.
# moving from one end of the range to the other takes a LONG time.
#
# home routine
# set units to counts (eg encoder)
# 1 sn 1
#enguage closed loop mode
# 1 mm 1
# closed loop timing 0.1s
# 1 cl 0.1
# move to neagtive limit
# 1 mt - 
# Set curent pos to 0
# 1 dh
# move back to mid position (need to check position)
# 1 pa 10000

class PicoMotorDevice(device.Device):
    """Newport picomotor controllers.

    The configuration section for these devices requires the following
    values:

    ``cal``
        Calibration.
    ``ipAddress``
        The IP address of the controller.
    ``port``
        The port the controller listens on.

    """
    _config_types = {
        'cal': float,
        'port': int,
    }
    def __init__(self, name, config):
        super().__init__(name, config)
        self.STAGE_CAL = config.get('cal') # e.g. 13.750
        self.PICO_CONTROLLER = config.get('ipaddress') # e.g. 172.16.0.30'
        self.PICO_PORT = config.get('port') # e.g. 23

        ## Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering which is 
        #x controller 1, motor 1 - '1>1'
        #y controller 1, motor 2 - '1>2'
        #z controller 2, motor 1 - '2>1'
        #Needs moving to config file!
        self.axisMapper = {0: '1>1', 1: '1>2', 2: '2>1'}

        ## Connection to the Z piezo controller (Pyro4.Proxy of a
        # telnetlib.Telnet instance)
        self.zConnection = None
        ## Lock around sending commands to the Z piezo controller.
        self.zLock = threading.Lock()
        ## Connection to the XY stage controller (serial.Serial instance)
        self.xyConnection = None
        ## Lock around sending commands to the XY stage controller.
        self.xyLock = threading.Lock()
        ## Cached copy of the stage's position. Initialized to an impossible
        # value; this will be modified in initialize.
        self.xyPositionCache = [10 ** 100, 10 ** 100,7500]

        events.subscribe(events.USER_ABORT, self.onAbort)


    def initialize(self):
        self.xyConnection=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.xyConnection.connect((self.PICO_CONTROLLER,self.PICO_PORT))

        #IMD 20130421 reset at startup as the cointroller can go a bit mad
        # Need long timeout as ethernet takes a while to come back up
        self.xyConnection.settimeout(2)
        result=self.sendXYCommand('RS',0)
        time.sleep(2)
        self.xyConnection.close()
        #restart the socket now we have rest the controller.
        self.xyConnection=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.xyConnection.connect((self.PICO_CONTROLLER,self.PICO_PORT))
        self.xyConnection.settimeout(1)
        
        #20130418 - the controller dumps a line of rubbish before we start...
        #give it time to wake up
        result=self.getXYResponse(1)   
        result=self.sendXYCommand('VE?',1)
#        print ("init controller firmware=", result)
        self.xyConnection.settimeout(2)

        # Get the proper initial position.
        #Need to init in some way here.
        #The home functions do this but are VERY slow
        self.getXYPosition(shouldUseCache = False)



    #Routine to home all 3 motors.
    #record position
    #move to negative threshold (z axis should go to +ve limit so
    #as not to ram objective)
    #check if moving, sleep and loop
    #record new pos
    #set home
    #move to start-end position to resturn to starting position
    #loop through each axis
    def homeMotors(self):
        origPosition=self.getXYPosition(shouldUseCache = False)
        for axis in range(0,2):
            print ("homeing axis 1 %s, origPosiiton=%d" % (self.axisMapper[axis], origPosition[axis]))
            (controller,motor)=self.axisMapper[axis].split('>')
            while self.checkForMotion(controller)==1:
                time.sleep(1)
            #Home this axis (to -ve home)
            self.sendXYCommand('%s mt -' %
                               (self.axisMapper[axis]),0)
            #wait for home to be done
            while(self.checkForMotion(controller)==1):
                time.sleep(1)
            #record new position                            
            newposition=self.getXYPosition(shouldUseCache = False)
            #set to pos zero
            self.sendXYCommand('%s dh ' %
                               (self.axisMapper[axis]),0)
            #move to pos +100 absolute to make sure we aren't in negative positions
            self.sendXYCommand('%s pa 100' %
                               (self.axisMapper[axis]),0)
            #calculate how to move back to where we were
            endpositon[axis]=-newposition[axis]+oldposition[axis]
                        
  
        print ("home done now returning to last position",endposition)
        for axis in range(0,2):
            while(self.checkForMotion(controller)==1):
                time.sleep(1)
            self.sendXYCommand('%s pa %s' %
                               (self.axisMapper[axis]),endposition[axis],0)
            

    ## Check for motion on a given controller. 
    def checkForMotion(self,controller):
        motorState1=self.sendXYCommand('%s>1 md' %
                                       (controller),1)
        motorState2=self.sendXYCommand('%s>2 md' %
                                       (controller),1)
        #need to split of controller number if we have more than one. Use
        #the format of axis 0 axisMapper string to check this. 
        if(len(self.axisMapper[0].split('>'))==2):
            motorState1 = motorState1.split('>')[1]
            motorState2 = motorState2.split('>')[1]

        return(motorState1 or motorState2)


#Routine to home all 3 motors.
#record position
#move to negative threshold (z axis should go to +ve limit so as not to ram objective)
#check if moving, sleep and loop
#record new pos
#set home
#move to start-end position to resturn to starting position
#loop through each axis


    def homeMotors(self):
        origPosition=self.getXYPosition(shouldUseCache = False)
        for axis in range(0,2):
            print ("homeing axis 1 %s, origPosiiton=%d" % (self.axisMapper[axis], origPosition[axis]))
            (controller,motor)=self.axisMapper[axis].split('>')
            while self.checkForMotion(controller)==1:
                time.sleep(1)
            #Home this axis (to -ve home)
            self.sendXYCommand('%s mt -' %
                               (self.axisMapper[axis]),0)
            #wait for home to be done
            while(self.checkForMotion(controller)==1):
                time.sleep(1)
            #record new position                            
            newposition=self.getXYPosition(shouldUseCache = False)
            #set to pos zero
            self.sendXYCommand('%s dh ' %
                               (self.axisMapper[axis]),0)
            #move to pos +100 absolute to make sure we aren't in negative positions
            self.sendXYCommand('%s pa 100' %
                               (self.axisMapper[axis]),0)
            #calculate how to move back to where we were
            endpositon[axis]=-newposition[axis]+oldposition[axis]
                        
  
        print ("home done now returning to last position",endposition)
        for axis in range(0,2):
            while(self.checkForMotion(controller)==1):
                time.sleep(1)
            self.sendXYCommand('%s pa %s' %
                               (self.axisMapper[axis]),endposition[axis],0)
            

    ## Send a command to the XY stage controller, read the response, check
    # for errors, and either raise an exception or return the response.
    # Very similar to sendZCommand of course, but xyConnection is a Serial
    # instance and zConnection is a Telnet instance.


    def checkForMotion(self,controller):
        motorState1=self.sendXYCommand('%s>1 md' %
                                       (controller),1)
        motorState1 = motorState1.split('>')[1]
        motorState2=self.sendXYCommand('%s>2 md' %
                                       (controller),1)
        motorState2 = motorState2.split('>')[1]
        return(motorState1 or motorState2)


    ## Send a command to the XY stage controller, read the response, check
    # for errors, and either raise an exception or return the response.
    def sendXYCommand(self, command, numExpectedLines = 1, shouldCheckErrors = True):
        with self.xyLock:
            self.xyConnection.sendall(command + '\n')
            #IMD 09052013 The controller needs a little time after a
            #command to digest it            
            time.sleep(0.05)
            if numExpectedLines>0:
                try :
                    response = self.xyConnection.recv(1024)
                except :
                    cockpit.util.logger.log.debug("in command %s, %d, No response",
                                              command,numExpectedLines)
                return response


    ## Read a response off of the XY connection. We do this one character
    # at a time in the hopes of avoiding having to wait for a timeout. We
    # stop when we hit the right number of newlines.
    def getXYResponse(self, numExpectedLines):
        response = ''
        numLines = 0
        while True:
            output = self.xyConnection.recv(1024)
            cockpit.util.logger.log.debug("Picomotor responce %s", output)
            response += output
            numLines += 1
            if numLines == numExpectedLines:
                break
            else:
                # No output; must be done.
                break
        return response


    ## When the user logs out close the network connection.
    def onExit(self):
        self.xyConnection.close()


    ## Halt motion when the user aborts. 
    def onAbort(self, *args):
        self.sendXYCommand('AB',0)


    def getHandlers(self):
        #IMD 20130418 hacked to include Z in this for the Picomovers stage
        result = []
        for axis, minPos, maxPos in [(0, -10000, 10000),
                    (1, -10000, 10000),(2,-1000,1000)]:
            result.append(cockpit.handlers.stagePositioner.PositionerHandler(
                    "%d PI mover" % axis, "%d stage motion" % axis, False,
                    {'moveAbsolute': self.moveXYAbsolute,
                         'moveRelative': self.moveXYRelative,
                         'getPosition': lambda axis=axis: self.getXYPosition(axis=axis),
                         'getMovementTime' :self.getXYMovementTime},
                    axis, (minPos, maxPos), (minPos, maxPos)))
        return result

    def getXYMovementTime(self,axis,start,end):
        distance=abs (end-start)
        #IMD15072014 closed loop performance is much slower, or counts != steps. 
        #speed is roughly 10,000 counts in 30 secs   
        return (((distance*self.STAGE_CAL)/300)+.25)

    def moveXYAbsolute(self, axis, pos):
        # IMD 20130418 need to calibrate stage properly, approx is 67 steps/um
        #IMD 20130530 suggest by Chris just flip X movemets to fix
        #wrong X and Y directions
        if (axis == 0) or (axis == 1):
            pos = -pos
        self.sendXYCommand('%s PA %d' %
                (self.axisMapper[axis], int (pos*self.STAGE_CAL) ),0)
        self.sendXYPositionUpdates()


    def moveXYRelative(self, axis, delta):
        # IMD 20130418 need to calibrate stage properly, approx is 67 steps/um
        # print "moving pr %d, %f",axis, delta
        if delta!=0 :
            #IMD 20130530 flip X axis to get correct direction.
            if (axis == 0) or (axis == 1):
                delta = -delta
                
            self.sendXYCommand('%s PR %d' %
                    (self.axisMapper[axis], int(delta*self.STAGE_CAL) ),0)
            self.sendXYPositionUpdates()


    ## Send updates on the XY stage's position, until it stops moving.
    @cockpit.util.threads.callInNewThread
    def sendXYPositionUpdates(self):
        prevX, prevY, prevZ = self.xyPositionCache
        while True:
            x, y, z = self.getXYPosition(shouldUseCache = False)
            delta = abs(x - prevX) + abs(y - prevY) + abs(z-prevZ)
            if delta < .3:
                # No movement since last time; done moving.
                for axis in [0, 1, 2]:
                    events.publish(events.STAGE_STOPPED, '%d PI mover' % axis)
                return
            for axis in [0, 1, 2]:
                events.publish(events.STAGE_MOVER, axis)
            (prevX, prevY, prevZ)= (x, y, z)
            time.sleep(0.1)


    ## Get the position of the specified axis, or all axes by default.
    # If shouldUseCache is not set, then we will query the controller, which
    # takes some time.
    def getXYPosition(self, axis = None, shouldUseCache = True):
        #+++        self.xyPositionCache = (0, 0,0)
        if not shouldUseCache:
            if axis is not None:
                position=self.sendXYCommand('%s TP?' % (self.axisMapper[axis]),
                                            1, False)
                if(len(self.axisMapper[axis].split('>'))==2):
                    position = position.split('>')[1]
                self.xyPositionCache[axis]=float(position)/self.STAGE_CAL
                return self.xyPositionCache[axis]                
            else:
                #axis is None so grab all positions. 
                for ax in range(len(self.axisMapper)):
                    position=self.sendXYCommand('%s TP?' %
                                                (self.axisMapper[ax]),
                                                1, False)
                    #have more than one controller so need to split
                    #controller number from position.
                    if(len(self.axisMapper[ax].split('>'))==2):
                        position = position.split('>')[1]
                    # Positions are in steps, and we need microns.
                    self.xyPositionCache[ax]=float(position)/self.STAGE_CAL

        #returning cached values, either single axis or all. 
        if axis is not None:
            return self.xyPositionCache[axis]
        else:
            return self.xyPositionCache



    def makeInitialPublications(self):
        self.sendXYPositionUpdates()
