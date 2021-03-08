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

"""Linkam stages."""

from cockpit import events
import cockpit.gui.guiUtils
import cockpit.gui.device
from cockpit.devices.microscopeDevice import MicroscopeBase
import cockpit.handlers.stagePositioner
import Pyro4
from cockpit.devices.device import Device
import threading
import cockpit.util.threads
from cockpit.util import valueLogger

import datetime
import time
import wx


DEFAULT_LIMITS = ((0, 0), (11000, 3000))
LOGGING_PERIOD = 30

class RefillTimerPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        self._refillFunc = None

        label_text = kwargs.pop('label', '')
        kwargs['style'] = kwargs.get('style', 0) | wx.BORDER_SIMPLE
        super().__init__(*args, **kwargs)
        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, wx.ID_ANY, label=label_text, style=wx.ALIGN_CENTRE_HORIZONTAL)
        # Create controls using label=self.format to set correct width.
        self.filling = wx.StaticText(self, wx.ID_ANY, label=self.format(None),
                                     style=wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE)
        self.previous = wx.StaticText(self, wx.ID_ANY, label=self.format(None),
                                      style=wx.ST_NO_AUTORESIZE)
        self.current = wx.StaticText(self, wx.ID_ANY, label=self.format(None),
                                     style= wx.ST_NO_AUTORESIZE)
        [self.Sizer.Add(o, flag=wx.ALL | wx.EXPAND, border=2) \
           for o in (label, self.previous, self.current, self.filling)]
        self.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)
        self.ToolTip = wx.ToolTip("dt: last cycle time.\nt+: time since last refill\nRight click to refill.")
        [c.Unbind(wx.EVT_MOTION) for c in self.Children]

    def setRefillFunc(self, f):
        self._refillFunc = f

    def onContextMenu(self, evt):
        menu = wx.Menu()
        menu.Append(1, "Start refill")
        self.Bind(wx.EVT_MENU, lambda e: self._refillFunc(), id=1)
        cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)


    def format(self, dt, prefix=""):
        prefix = '{:3.3} '.format(prefix)
        if dt is None:
            return prefix + "--:--:--"
        elif isinstance(dt, datetime.timedelta):
            dt = dt.total_seconds()
        mm, ss = divmod(dt, 60)
        hh, mm = divmod(mm, 60)
        return prefix + ("%.2d:%.2d:%.2d" % (hh, mm, ss))

    def doUpdate(self, refill):
        # Default colours for current timer display. May be modified before
        # being set at the end of this call.
        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        if refill is None:
            self.previous.SetLabel(self.format(None, 'dt'))
            self.current.SetLabel(self.format(None, 't+'))
        else:
            # Counters
            t_last = refill.get('last') # May be None
            prev = refill.get('between_last').total_seconds() # Always datetime.timedelta
            self.previous.SetLabel(self.format(prev, 'dt'))
            if t_last is None:
                self.current.SetLabel(self.format(None, 't+'))
            else:
                t = (datetime.datetime.now() - t_last).total_seconds()
                self.current.SetLabel(self.format(t, 't+'))
                if prev > 0:
                    if (prev - t) <= 60:
                        # 1 minute left
                        bg = wx.Colour("red")
                        fg = wx.Colour("white")
                    elif (prev - t) < 300:
                        # 5 minutes left
                        bg = wx.Colour("yellow")
                        fg = wx.Colour("black")
            # Refill indicator
            if refill.get('refilling', False):
                self.filling.SetLabel("REFILLING")
                bg = wx.Colour("red")
                fg = wx.Colour("white")
            else:
                self.filling.SetLabel(" ")
        if bg != self.GetBackgroundColour():
            self.SetBackgroundColour(bg)
            for c in self.GetChildren():
                c.SetForegroundColour(fg)
            self.Refresh()


class LinkamStage(MicroscopeBase, Device):
    """Cockpit-side module for Linkam stages.

    Tested with CMS196.  Config uses following parameters:

    ``type``
        Needs to be ``cockpit.devices.linkamStage.LinkamStage``.
    ``uri``
        URI of device server.

    """

    _temperature_names = ('bridge', 'dewar', 'chamber', 'base')
    _refill_names = ('sample', 'external')

    def __init__(self, name, config={}):
        super().__init__(name, config)
        ## Connection to the XY stage controller (serial.Serial instance).
        self._proxy = Pyro4.Proxy(config.get('uri'))
        ## Lock around sending commands to the XY stage controller.
        self.xyLock = threading.Lock()
        ## Cached copy of the stage's position.
        self.positionCache = (None, None)
        ## Target positions for movement in X and Y.
        self.motionTargets = [None, None]
        ## Flag to show that sendPositionUpdates is running.
        self.sendingPositionUpdates = False
        ## Status dict updated by remote.
        self.status = {}
        ## Keys for status items that should be logged
        self.logger = valueLogger.ValueLogger(name, keys=list(map('t_'.__add__, self._temperature_names)))
        try:
            xlim = self._proxy.get_value_limits('MotorSetpointX')
            ylim = self._proxy.get_value_limits('MotorSetpointY')
        except:
            xlim, ylim = zip(*DEFAULT_LIMITS)
        # _proxy may return (0,0) if it can't query the hardware.
        if not any (xlim):
            xlim, _ = zip(*DEFAULT_LIMITS)
        if not any (ylim):
            _, ylim = zip(*DEFAULT_LIMITS)
        self.hardlimits = tuple(zip(xlim, ylim))
        self.softlimits = self.hardlimits

        events.subscribe(events.USER_ABORT, self.onAbort)


    def finalizeInitialization(self):
        """Finalize device initialization."""
        self.statusThread = threading.Thread(target=self.pollStatus, name="Linkam-status")
        events.subscribe('cockpit initialization complete', self.statusThread.start)


    def pollStatus(self):
        """Fetch the status from the remote and update the UI.

        Formerly, the remote periodically pushed status to a cockpit
        server. This caused frequent Pyro timeout errors when cockpit
        was busy doing other things.
        """
        lastTemps = [None]
        lastTime = 0

        while True:
            time.sleep(1)
            try:
                status = self._proxy.get_status()
            except Pyro4.errors.ConnectionClosedError:
                # Some dumb Pyro bug.
                continue

            if status.get('connected', False):
                self.status.update(status)
                self.sendPositionUpdates()
                tNow = time.time()
                if tNow - lastTime > LOGGING_PERIOD:
                    newTemps = [status.get(k) for k in self.logger.keys]
                    from operator import eq
                    if not all(map(eq, newTemps, lastTemps)):
                        self.logger.log(newTemps)
                        lastTemps = newTemps
                    lastTime = tNow
            else:
                self.status['connected'] = False
            self.updateUI()


    def initialize(self):
        """Initialize the device."""
        self.getPosition(shouldUseCache = False)
        self.updateSettings()


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
                         'getPosition': self.getPosition},
                    axis,
                    (minPos, maxPos), # hard limits
                    (minPos, maxPos) # soft limits
                    )
                )
        return result


    def makeUI(self, parent):
        """Make cockpit user interface elements."""
        ## A list of value displays for temperatures.
        # Panel, sizer and a device label.
        self.panel = wx.Panel(parent, style=wx.BORDER_RAISED)
        self.panel.SetDoubleBuffered(True)
        panel = self.panel
        panel.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.Sizer.Add(left_sizer)
        panel.Sizer.Add(right_sizer)

        self.elements = {}
        lightButton = wx.ToggleButton(panel, wx.ID_ANY, "light")
        lightButton.Bind(wx.EVT_TOGGLEBUTTON,
                         lambda evt: self._proxy.set_light(evt.EventObject.Value))
        self.elements['light'] = lightButton
        left_sizer.Add(lightButton, flag=wx.EXPAND)
        condensorButton = wx.ToggleButton(panel, wx.ID_ANY, "condensor")
        condensorButton.Bind(wx.EVT_TOGGLEBUTTON,
                             lambda evt: self._proxy.set_condensor(evt.EventObject.Value))
        left_sizer.Add(condensorButton, flag=wx.EXPAND)
        ## Generate the value displays.
        for d in self._temperature_names:
            self.elements[d] = cockpit.gui.device.ValueDisplay(
                    parent=panel, label=d, value=0.0, 
                    formatStr="%.1f", unitStr=u'°C')
            left_sizer.Add(self.elements[d])
        # Settings button
        adv_button = wx.Button(parent=self.panel, label='settings')
        adv_button.Bind(wx.EVT_LEFT_UP, self.showSettings)
        left_sizer.Add(adv_button, flag=wx.EXPAND)
        # Refill timers
        for r in self._refill_names:
            self.elements[r] = RefillTimerPanel(panel, wx.ID_ANY, label=r)
            right_sizer.Add(self.elements[r], flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=4)
            if r == 'sample':
                self.elements[r].setRefillFunc(self._proxy.refill_chamber)
            elif r == 'external':
                self.elements[r].setRefillFunc(self._proxy.refill_dewar)
        panel.Fit()
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
            self._proxy.move_to(*newPos)
        self.motionTargets[axis] = pos
        self.sendPositionUpdates()


    def moveRelative(self, axis, delta):
        """Move stage to a position relative to the current position."""
        if delta:
            curPos = self.positionCache[axis]
            self.moveAbsolute(axis, curPos + delta)


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
            # Update position cache before publishing STAGE_MOVER so
            # that the UI gets the new position when it queries it.
            self.getPosition(shouldUseCache=False)
            for axis in [0, 1]:
                events.publish(events.STAGE_MOVER, axis)
            moving = self._proxy.is_moving()

        for axis in (0, 1):
            events.publish(events.STAGE_STOPPED, '%d linkam mover' % axis)
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
                    position = self._proxy.get_position()
                    success = True
                except Pyro4.errors.ConnectionClosedError:
                    if failCount < 5:
                        failCount += 1
                    else:
                        raise
                except:
                    raise
            self.positionCache = (position['X'], position['Y'])
        if axis is None:
            return self.positionCache
        else:
            return self.positionCache[axis]


    def updateUI(self):
        """Update user interface elements."""
        status = self.status
        if not status.get('connected', False):
            self.panel.Disable()
            return
        self.panel.Enable()
        # Temperatures
        for t in self._temperature_names:
            self.elements[t].update(self.status.get('t_' + t))
        self.elements['light'].SetValue(status.get('light', False))
        # Refills
        lines = []
        now = datetime.datetime.now()

        for r in self._refill_names:
            refill = status['refills'].get(r, None)
            self.elements[r].doUpdate(refill)


    def makeInitialPublications(self):
        """Send initial device publications."""
        self.sendPositionUpdates()
