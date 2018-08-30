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


"""cockpit.gui.valueLogger

Adds a logging window to cockpit.
"""
from cockpit import events
import cockpit.interfaces.valueLogger
import cockpit.gui.guiUtils
import cockpit.gui.keyboard
import cockpit.util.files
import matplotlib
import matplotlib.dates
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure
import cockpit.util.threads
import cockpit.util.userConfig
import wx
import datetime
import os

from six.moves import reduce

USER_CONFIG_ENTRY = 'ValueLogger.showKeys'


class ValueLoggerWindow(wx.Frame):
    """A window that shows logged values."""
    def __init__(self, parent):
        super(ValueLoggerWindow, self).__init__(parent, title='Value logger')
        ## A mapping of names to booleans.
        self.showKeys = {}
        ## A mapping of name to line objects.
        self.lines = {}
        ## A mapping of name to labels.
        self.labels = {}
        ## A filehandle to use for logging values to file.
        self.filehandle = cockpit.interfaces.valueLogger.instance.filehandle
        ## Flag to say if we are logging values to file or not. 
        self.logToFile = False
        ## matplotlib objects
        self.figure = Figure()
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, self.figure)
        ## Border around axes in pixels (left, bottom, right, top)
        self.border = (56, 56, 24, 24)
        ## Main panel sizer.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        ## Data sources
        self.dataTimes = cockpit.interfaces.valueLogger.instance.times
        self.dataSeries = cockpit.interfaces.valueLogger.instance.series

        # Add the canvas to the sizer.
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        self.SetSizer(self.sizer)
        # Show a menu of available data on right mouse click.
        self.canvas.Bind(wx.EVT_RIGHT_DOWN, self.onRightMouse)
        # Bind to our resize handler.
        self.Bind(wx.EVT_SIZE, self.onResize)

        ## Set axis properties.
        self.axes.xaxis_date()
        self.axes.xaxis.set_major_formatter(
                matplotlib.dates.DateFormatter('%H:%M'))
        self.axes.xaxis.set_major_locator(
                matplotlib.ticker.LinearLocator() )

        ## Set intial figure borders.
        self.setFigureBorder(self.Size)

        ## Subscribe to new logged values available events.
        events.subscribe("valuelogger update", self.draw)
        ## Subscribe to user login events.
        events.subscribe("user login", self.loadShowKeysFromConfig)

        # Add cockpit window bindings to this window.
        cockpit.gui.keyboard.setKeyboardHandlers(self)
        self.SetSizeHints(600, 400)
        self.Show()
        

    def setFigureBorder(self, size):
        """Set the figure border from the window size."""
        border = self.border # (left, bottom, right, top)
        
        pos = (float(self.border[0]) / size[0],
               float(self.border[1]) / size[1],
               1 - float(self.border[2] + self.border[0]) / size[0],
               1 - float(self.border[3] + self.border[1]) / size[1])
        self.axes.set_position(pos)


    def onResize(self, event):
        """Resize event handler."""
        self.setFigureBorder(event.Size)
        event.Skip()
        

    def onRightMouse(self, *args):
        """Show a menu of available data on right mouse click."""
        menu = wx.Menu()
        i = 1
        #if no logfile open then show openlogfile option
        if self.filehandle==None:
            menu.Append(i, 'Open logfile.')
            menu.Bind(wx.EVT_MENU,  lambda event:self.openLogFile(), id= i)
        else:
            #close logfile option
            menu.Append(i, 'Close logfile.')
            menu.Bind(wx.EVT_MENU,  lambda event:self.closeLogFile(), id= i)

        i += 1
        menu.AppendSeparator()
        for key, enabled in sorted(self.showKeys.items() ):
            if key not in self.dataSeries:
                continue
            menu.Append(i, key, '', wx.ITEM_CHECK)
            menu.Check(i, enabled)
            menu.Bind(wx.EVT_MENU,  lambda event, k=key:self.toggleShowKey(k), id= i)
            i += 1
        cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)

    
    def draw(self, *args):
        """Plot the data.

        All the leg work can be done in any thread, but the canvas.show
        call must be in the main wx thread.
        """
        if not window:
            # If there is no window, there is nothing to do.
            return
        dataTimes = self.dataTimes
        dataSeries = self.dataSeries
        
        for (key, series) in dataSeries.items():
            if key == 'time':
                # Don't plot time vs time.
                continue
            if not self.showKeys:
                # If showKeys is empty, create one True entry.
                self.showKeys[key] = True
            elif key not in self.showKeys:
                # Require explicit instruction to show other items.
                self.showKeys[key] = False

            if self.showKeys[key]:
                # This line should be shown.
                # See if there is any good data.
                lastPoint = reduce(
                        lambda last, i: i if series[i] is not None else last,
                        range(len(series)), -1)
                if lastPoint == -1:
                    showLine = False
                else:
                    showLine = True
            else:
                showLine = False

            if showLine:
                # The line should and can be shown.
                line = self.lines.get(key, None)
                if line:
                    # If the line exists, update the data.
                    line.set_data(dataTimes, series)
                else:
                    # Otherwise, create the line.
                    line, = self.axes.plot(dataTimes, series)
                    self.lines[key] = line

                # Update the label.
                label = self.labels.get(key, None)
                if label:
                    # The label exists. Make it track the last good point.
                    self.labels[key].set_y(series[lastPoint])
                else:
                    # The label does not yet exist. Create it.
                    self.labels[key] = self.axes.text(
                            dataTimes[-1], 
                            series[lastPoint], 
                            ' %s' % key,
                            ha='right',
                            color=self.lines[key].get_color())
            else:
                # The line should not or can not be shown.
                line = self.lines.get(key, None)
                label = self.labels.get(key, None)
                if line:
                    # If it exists, remove it from the graph.
                    self.axes.lines.remove(line)
                    del(self.lines[key])
                if label:
                    # If the label exists, remove it.
                    self.axes.texts.remove(label)
                    del(self.labels[key])
        # Update the axes so that the current data sets fit.
        xaxis = self.axes.xaxis
        if self.lines:
            self.axes.relim()
            self.axes.autoscale_view()
            # Put each series label at the far right of the axes.
            xMax = xaxis.get_view_interval()[1]
            for label in self.labels.values():
                label.set_x(xMax)
        # Rotate each tick mark
        ticksMajor = xaxis.get_ticklabels()
        ticksMinor = xaxis.get_ticklabels(minor=True)
        for tick in ticksMajor + ticksMinor:
            tick.set_rotation(90)
        # Update the canvas in the main wx thread.
        self._doDraw()


    @cockpit.util.threads.callInMainThread
    def _doDraw(self):
        self.canvas.draw()
        #self.canvas.flush_events()


    def loadShowKeysFromConfig(self, event):
        """Load which traces to show from config."""
        showKeys = cockpit.util.userConfig.getValue(USER_CONFIG_ENTRY)
        if showKeys:
            self.showKeys = showKeys


    def saveShowKeysToConfig(self):
        """Save which traces to show to config."""
        cockpit.util.userConfig.setValue(USER_CONFIG_ENTRY, (self.showKeys))

        
    def toggleShowKey(self, key):
        """Toggle the state of an entry in showKeys."""
        self.showKeys[key] = not self.showKeys[key]
        

    # File logging code.
    def openLogFile(self):
        """Open a log file"""
        if self.filehandle is None:
            cockpit.interfaces.valueLogger.instance.filehandle=open(
                self.generateLogFilename(),'w')
            self.filehandle=cockpit.interfaces.valueLogger.instance.filehandle
        else:
            #file already open
            pass


    def closeLogFile(self):
        """Close the open logfile"""
        if self.filehandle is not None:
            cockpit.interfaces.valueLogger.instance.filehandle.close
            self.filehandle=None

    def generateLogFilename(self):
        timestr=datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename="ValueLog"+timestr+".log"
        filename = os.path.join(cockpit.util.files.getLogDir(), filename)
        return filename

        

def makeWindow(parent):
    """Create the ValueLogger window instance and associated objects."""
    # The ValueLoggerWindow instance.
    global window
    window = ValueLoggerWindow(parent)
