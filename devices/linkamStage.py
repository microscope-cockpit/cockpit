# coding: utf-8
"""pyLinkam

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
Cockpit-side module for Linkam stages. Tested with CMS196.
"""
import depot
import device
import events
import gui.guiUtils
import gui.device
import gui.toggleButton
import handlers.stagePositioner
import interfaces
import Pyro4
import threading
import util.logger as logger
import util.threads
import util.userConfig

import time
import wx
import re # to get regular expression parsing for config file

from config import config
CLASS_NAME = 'CockpitLinkamStage'

CONFIG_NAME = 'linkam'
LIMITS_PAT = r"(?P<limits>\(\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*\,\s*[-]?\d*\s*\)\))"
DEFAULT_LIMITS = ((0, 0), (11000, 3000))

class CockpitLinkamStage(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Connection to the XY stage controller (serial.Serial instance).
        self.remote = None
        ## Lock around sending commands to the XY stage controller.
        self.xyLock = threading.Lock()
        ## Cached copy of the stage's position.
        self.positionCache = (None, None)
        ## Target positions for movement in X and Y.
        self.motionTargets = [None, None]
        ## Time of last action using the stage.
        self.lastPiezoTime = time.time()
        ## Stage velocity
        self.stageVelocity = [None, None]
        ## Flag to show that sendPositionUpdates is running.
        self.sendingPositionUpdates = False

        self.isActive = config.has_section(CONFIG_NAME)
        if self.isActive:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))
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
                logger.log.warn('Could not parse limits from config: using defaults.')
                print "No softlimits section setting default limits"
                self.softlimits = DEFAULT_LIMITS
            events.subscribe('user logout', self.onLogout)
            events.subscribe('user abort', self.onAbort)


    @util.threads.locked
    def finalizeInitialization(self):
        # Open an incoming connection with the remote object.
        server = depot.getHandlersOfType(depot.SERVER)[0]
        uri = server.register(self.receiveStatus)
        self.remote.setClient(uri)


    def receiveStatus(self, status):
        pass


    def initialize(self):
        uri = "PYRO:%s@%s:%d" % (CONFIG_NAME, self.ipAddress, self.port)
        self.remote = Pyro4.Proxy(uri)
        self.remote.connect()
        self.getPosition(shouldUseCache = False)
        

    def homeMotors(self):
        """Home the motors."""
        self.remote.homeMotors()
        self.sendPositionUpdates()


    def onLogout(self, *args):
        pass
        

    def onAbort(self, *args):
        """Stop motion immediately."""
        pass


    def getHandlers(self):
        result = []
        # zip(*limits) transforms ((x0,y0),(x1,y1)) to ((x0,x1),(y0,y1))
        for axis, (minPos, maxPos) in enumerate(zip(*self.softlimits)):
            result.append(
                handlers.stagePositioner.PositionerHandler(
                    "%d linkam mover" % axis, "%d stage motion" % axis, False,
                    {'moveAbsolute': self.moveAbsolute,
                         'moveRelative': self.moveRelative,
                         'getPosition': self.getPosition,
                         'setSafety': self.setSafety},
                    axis,
                    [1, 2, 5, 10, 50, 100, 200], # step sizes
                    3, # initial step size index,
                    (minPos, maxPos), # soft limits
                    (minPos, maxPos) # hard limits
                    )
                )
        return result


    def makeUI(self, parent):
        """Make cockpit user interface elements."""
        ## A list of value displays for temperatures.
        tempDisplays = ['bridge', 'chamber', 'dewar']
        # Panel, sizer and a device label.
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(parent=panel,
                                label='cryostage')
        sizer.Add(label)
        ## Generate the value displays.
        self.displays = {}
        for d in tempDisplays:
            self.displays[d] = gui.device.ValueDisplay(
                    parent=panel, label=d, value=0.0, 
                    unitStr=u'°C')
            sizer.Add(self.displays[d])
        ## Set the panel sizer and return.
        panel.SetSizerAndFit(sizer)
        return panel


    def moveAbsolute(self, axis, pos):
        """Move a stage axis to new position, pos."""
        pos = int(pos)
        if axis == 0:
            newPos = (pos, None)
        elif axis == 1:
            newPos = (None, pos)
        else:
            # Arguments were wrong. Just return, since raising an
            # exception can kill the mosaic.
            return
        with self.xyLock:
            # moveToXY(x, y), where None indicates no change.
            self.remote.moveToXY(*newPos)
        self.motionTargets[axis] = pos
        self.sendPositionUpdates()


    def moveRelative(self, axis, delta):
        if delta:
            curPos = self.positionCache[axis]
            self.moveAbsolute(axis, curPos + delta)


    @util.threads.callInNewThread
    def sendPositionUpdates(self):
        """Send XY stage positions until it stops moving."""
        if self.sendingPositionUpdates is True:
            # Already sending updates.
            return
        self.sendingPositionUpdates = True
        moving = True
        # Send positions at least once.
        while moving:
            coords = self.getPosition(shouldUseCache=False)
            for axis, value in enumerate(coords):
                events.publish('stage mover',
                               '%d linkam mover' % axis, 
                               axis, value)
            moving = self.remote.isMoving()
            # Need this thread to sleep to give UI a chance to update.
            time.sleep(0.1)

        for axis in (0, 1):
            events.publish('stage stopped', '%d linkam mover' % axis)
            self.motionTargets = [None, None]
        self.sendingPositionUpdates = False
        return


    def getPosition(self, axis=None, shouldUseCache=True):
        """Return the position of one or both axes.

        If axis is None, return positions of both axes.
        Query the hardware if shouldUseCache is False.
        """
        if not shouldUseCache:
            position = self.remote.getPosition()
            self.positionCache = position
        if axis is None:
            return self.positionCache
        else:
            return self.positionCache[axis]


    def setSafety(self, axis, value, isMax):
        pass


    def makeInitialPublications(self):
        self.sendPositionUpdates()
