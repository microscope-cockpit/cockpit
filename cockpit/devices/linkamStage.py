#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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


"""pyLinkam

Cockpit-side module for Linkam stages. Tested with CMS196.

Config uses following parameters:
  type:         LinkamStage
  ipAddress:    address of pyLinkam remote
  port:         port that remote is listening on
  primitives:   list of _c_ircles and _r_ectangles to draw on MacroStageXY 
                view, defining one per line as
                    c x0 y0 radius
                    r x0 y0 width height
"""
from cockpit import events
import cockpit.gui.guiUtils
import cockpit.gui.device
import cockpit.gui.toggleButton
import cockpit.handlers.stagePositioner
import Pyro4
from . import stage
import threading
import cockpit.util.logger as logger
import cockpit.util.threads

import time
import wx
import re # to get regular expression parsing for config file

LIMITS_PAT = r"(?P<limits>\(\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*\,\s*[-]?\d*\s*\)\))"
DEFAULT_LIMITS = ((0, 0), (11000, 3000))
TEMPERATURE_LOGGING = False

class LinkamStage(stage.StageDevice):
    def __init__(self, name, config={}):
        super(LinkamStage, self).__init__(name, config)
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
        ## Status dict updated by remote.
        self.status = {}
        ## Flag to show UI has been built.
        self.hasUI = False
        try :
            limitString = config.get('softlimits', '')
            parsed = re.search(LIMITS_PAT, limitString)
            if not parsed:
                # Could not parse config entry.
                raise Exception('Bad config: Linkam Limits.')
                # No transform tuple
            else:
                lstr = parsed.groupdict()['limits']
                self.softlimits=eval(lstr)
        except:
            logger.log.warning('Could not parse limits from config: using defaults.')
            print ("No softlimits section setting default limits")
            self.softlimits = DEFAULT_LIMITS
        events.subscribe('user logout', self.onLogout)
        events.subscribe('user abort', self.onAbort)
        #store and recall condensor LED status.
        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
         #hack as no way to read state at the momnent. Need to FIX.
         settings[self.name] = {'condensor': 0 }

    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            #Only chnbage settings if needed.
            if settings[self.name]['condensor']:
                self.condensorOn()
            else:
                self.condensorOff()

    def finalizeInitialization(self):
        """Finalize device initialization."""
        self.statusThread = threading.Thread(target=self.pollStatus)
        events.subscribe('cockpit initialization complete', self.statusThread.start)


    def pollStatus(self):
        """Fetch the status from the remote and update the UI.

        Formerly, the remote periodically pushed status to a cockpit
        server. This caused frequent Pyro timeout errors when cockpit
        was busy doing other things.
        """
        #create a fill timer
        events.publish('new status light','Fill Timer','')
        self.lastFillCycle = 0
        self.lastFillTimer = 0
        self.timerbackground = (170, 170, 170)
        
        while True:
            time.sleep(1)
            try:
                status = self.remote.getStatus()
            except Pyro4.errors.ConnectionClosedError:
                # Some dumb Pyro bug.
                continue

            if not status.get('connected', False):
                keys = set(status.keys()).difference(set(['connected']))
                self.status.update(map(lambda k: (k, None), keys))
                self.status['connected'] = False
            else:
                self.status.update(status)
            events.publish("status update", __name__, self.status)
            self.sendPositionUpdates()
            self.updateUI()
            #update fill timer status light
            timeSinceFill = self.status.get('timeSinceMainFill')
            if (timeSinceFill is not None):			
                if( timeSinceFill > (0.9*self.lastFillCycle)):
                    self.timerbackground = (190, 0, 0)
                if( timeSinceFill < self.lastFillTimer ):
                    #refilled so need to reset cycle time and background
                    self.lastFillCycle = self.lastFillTimer
                    self.timerbackground = (170, 170, 170)
                events.publish('update status light','Fill Timer',
                                'Fill Timer\n%2d:%02d/%2d:%02d' %(
                                int(timeSinceFill/60.0),
                                timeSinceFill%60.0,
                                int(self.lastFillCycle/60.0),
                                self.lastFillCycle%60.0),
                                self.timerbackground)
                self.lastFillTimer = timeSinceFill

            if not TEMPERATURE_LOGGING:
                continue

            newTemps = '%.1f\t%.1f\t%.1f' % (self.status.get('dewarT'),
                                             self.status.get('chamberT'),
                                             self.status.get('bridgeT'))
            if not hasattr(self, 'lastTemps'):
                self.lastTemps = ''
            if self.lastTemps != newTemps:
                with open('linkLog.txt', 'a') as f:
                    f.write('%f\t%s\n' % (self.status.get('time'), newTemps))
                self.lastTemps = newTemps

    def initialize(self):
        """Initialize the device."""
        uri = "PYRO:%s@%s:%d" % ('linkam', self.ipAddress, self.port)
        self.remote = Pyro4.Proxy(uri)
        # self.remote.connect()
        self.getPosition(shouldUseCache = False)
        

    def homeMotors(self):
        """Home the motors."""
        self.remote.homeMotors()
        self.sendPositionUpdates()


    def onLogout(self, *args):
        """Cleanup on user logout."""
        pass
        

    def onAbort(self, *args):
        """Actions to do in the event of an abort."""
        pass


    def getHandlers(self):
        """Generate and return device handlers."""
        result = []
        # zip(*limits) transforms ((x0,y0),(x1,y1)) to ((x0,x1),(y0,y1))
        for axis, (minPos, maxPos) in enumerate(zip(*self.softlimits)):
            result.append(
                cockpit.handlers.stagePositioner.PositionerHandler(
                    "%d linkam mover" % axis, "%d stage motion" % axis, False,
                    {'moveAbsolute': self.moveAbsolute,
                         'moveRelative': self.moveRelative,
                         'getPosition': self.getPosition,
                         'setSafety': self.setSafety, 
                         'getPrimitives': self.getPrimitives},
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
        self.panel = wx.Panel(parent)
        self.panel.SetDoubleBuffered(True)
        panel = self.panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = cockpit.gui.device.Label(parent=panel,
                                label='Cryostage')
        sizer.Add(label)
        self.elements = {}
        lightButton = cockpit.gui.toggleButton.ToggleButton(
                parent=panel,
                label='chamber light',
                size=cockpit.gui.device.DEFAULT_SIZE,
                activateAction=self.toggleChamberLight,
                deactivateAction=self.toggleChamberLight,
                isBold=False)
        self.elements['light'] = lightButton
        sizer.Add(lightButton)
        condensorButton = cockpit.gui.toggleButton.ToggleButton(
                parent=panel,
                label='condensor LED',
                size=cockpit.gui.device.DEFAULT_SIZE,
                activateAction=self.condensorOn,
                deactivateAction=self.condensorOff,
                isBold=False)
        self.elements['condensor'] = condensorButton
        sizer.Add(condensorButton)
        ## Generate the value displays.
        for d in tempDisplays:
            self.elements[d] = cockpit.gui.device.ValueDisplay(
                    parent=panel, label=d, value=0.0, 
                    unitStr=u'°C')
            sizer.Add(self.elements[d])
        panel.Bind(wx.EVT_CONTEXT_MENU, self.onRightMouse)

        ## Set the panel sizer and return.
        panel.SetSizerAndFit(sizer)
        self.hasUI = True
        return panel


    def menuCallback(self, index, item):
        p = r'(?P<speed>[0-9]*)./s'
        if item.lower() == 'home stage':
            self.homeMotors()
            return
        elif re.match(p, item):
            speed = int(re.match(p, item).groupdict()['speed'])
            self.remote.setMotorSpeed(speed)
        else:
            return


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
        """Move stage to a position relative to the current position."""
        if delta:
            curPos = self.positionCache[axis]
            self.moveAbsolute(axis, curPos + delta)


    def onRightMouse(self, event):
        items = ['Home stage', '',
                 'Motor speed', u'100µ/s', u'200µ/s', u'300µ/s',
                 u'400µ/s', u'500µ/s', '', 'Cancel']
        menu = cockpit.gui.device.Menu(items, self.menuCallback)
        menu.Enable(2, False)
        menu.show(event)


    @cockpit.util.threads.callInNewThread
    def sendPositionUpdates(self):
        """Send XY stage positions until it stops moving."""
        if self.sendingPositionUpdates is True:
            # Already sending updates.
            return
        self.sendingPositionUpdates = True
        moving = True
        # Send positions at least once.
        while moving:
            # Need this thread to sleep to give UI a chance to update.
            # Sleep at start of loop to allow stage time to respond to
            # move request so remote.isMoving() returns True.
            time.sleep(0.1)
            coords = self.getPosition(shouldUseCache=False)
            for axis, value in enumerate(coords):
                events.publish('stage mover',
                               '%d linkam mover' % axis, 
                               axis, value)
            moving = self.remote.isMoving()

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
            # Occasionally, at the start on an experiment, a
            # ConnectionClosedError is thrown here. I think this is something
            # to do with Pyro reusing connections and those connections getting
            # closed on the remote due to frequent traffic in the status thread.
            # Workaround: retry a few times in the event of a ConnectionClosedError.
            success = False
            failCount = 0
            while not success:
                try:
                    position = self.remote.getPosition()
                    success = True
                except Pyro4.errors.ConnectionClosedError:
                    if failCount < 5:
                        failCount += 1
                    else:
                        raise
                except:
                    raise
            self.positionCache = position
        if axis is None:
            return self.positionCache
        else:
            return self.positionCache[axis]


    def setSafety(self, axis, value, isMax):
        """Set safety limits on range of motion."""
        pass


    def toggleChamberLight(self):
        self.remote.toggleChamberLight()


    def condensorOff(self):
        self.remote.setCondensorLedLevel(0)


    def condensorOn(self):
        self.remote.setCondensorLedLevel(1)


    def updateUI(self):
        """Update user interface elements."""
        if not self.hasUI:
            # UI not built yet
            return
        status = self.status
        self.elements['bridge'].update(self.status.get('bridgeT'))
        self.elements['chamber'].update(self.status.get('chamberT'))
        self.elements['dewar'].update(self.status.get('dewarT'))
        ## The stage SDK allows us to toggle the light, but not know
        # its state.
        # self.elements['light'].setActive(not self.status.get('light'))
        valuesValid = status.get('connected', False)
        if valuesValid:
            self.panel.Enable()
        else:
            self.panel.Disable()


    def makeInitialPublications(self):
        """Send initial device publications."""
        self.sendPositionUpdates()
