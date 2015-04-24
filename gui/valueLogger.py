# coding: utf-8
"""gui.valueLogger

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

Adds a logging window to cockpit.
"""
import events
import interfaces.valueLogger
import gui.guiUtils
import matplotlib
import matplotlib.dates
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import threading
import time
import wx


class ValueLoggerWindow(wx.Frame):
    """The main ValueLogger window."""
    def __init__(self, parent, title='value logger'):
        super(ValueLoggerWindow, self).__init__(
                parent, -1, title,
                style = wx.CAPTION | wx.RESIZE_BORDER)
        # Bind to close event.
        self.Bind(wx.EVT_CLOSE, self.onClose)
        # Create our panel.
        self.panel = ValueLoggerPanel(self)
        self.Show()


    def onClose(self, *args):
        window = None
        self.panel.Destroy()
        self.Destroy()


class ValueLoggerPanel(wx.Panel):
    """A panel for ValueLoggerWindow."""
    def __init__(self, parent):
        super(ValueLoggerPanel, self).__init__(parent)
        ## A mapping of names to booleans.
        self.showKeys = {}
        ## A mapping of name to line objects.
        self.lines = {}
        ## A mapping of name to labels.
        self.labels = {}
        ## matplotlib objects
        self.figure = Figure()
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, self.figure)
        ## Border around axes in pixels (left, bottom, right, top)
        self.border = (56, 88, 192, 24)
        ## Main panel sizer.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Add the canvas to the sizer.
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        self.SetSizer(self.sizer)
        self.sizer.SetSizeHints(parent)
        # Redraw when new logged values are available.
        events.subscribe("valuelogger update", self.draw)
        # Show a menu of available data on right mouse click.
        self.canvas.Bind(wx.EVT_RIGHT_DOWN, self.onRightMouse)
        # Bind to our resize handler.
        self.Bind(wx.EVT_SIZE, self.onResize)

        ## Set axis properties.
        self.axes.xaxis_date()
        self.axes.xaxis.set_major_formatter(
                matplotlib.dates.DateFormatter('%H:%M:%S'))
        self.axes.xaxis.set_major_locator(
                matplotlib.ticker.LinearLocator() )

        ## Set intial figure borders.
        self.setFigureBorder(self.Size)
        

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
        for i, (key, enabled) in enumerate(sorted(self.showKeys.items())):
            menu.Append(i, key, '', wx.ITEM_CHECK)
            menu.Check(i, enabled)
            wx.EVT_MENU(menu, i, lambda event, k=key:self.toggleShowKey(k))
        gui.guiUtils.placeMenuAtMouse(self, menu)

    
    def draw(self, *args):
        """Plot the data."""
        if not window:
            # If there is no window, there is nothing to do.
            return

        dataTimes = interfaces.valueLogger.instance.times
        dataSeries = interfaces.valueLogger.instance.series
        for (key, series) in dataSeries.iteritems():
            if key == 'time':
                # Don't plot time vs time.
                continue
            if not self.showKeys:
                # If showKeys is empty, create one True entry.
                self.showKeys[key] = True
            elif key not in self.showKeys:
                # Require explicit instruction to show other items.
                self.showKeys[key] = False

            line = self.lines.get(key, None)
            if self.showKeys[key]:
                # If we are to show this line ...
                if line:
                    # if the line exists, update the data
                    line.set_data(dataTimes, series)
                    # Make the series label track the most recent value.
                    self.labels[key].set_y(series[-1])
                elif len(series) > 0:
                    # otherwise, create the line if there is data available.
                    self.lines[key], = self.axes.plot(
                            dataTimes, 
                            series)
                    self.labels[key] = self.axes.text(dataTimes[-1], 
                                                      series[-1], 
                                                      ' %s' % key)
            else:
                # We don't want to show this line.
                if line:
                    # If it exists, remove it from the graph.
                    self.axes.lines.remove(line)
                    self.lines[key] = None
        # Update the axes so that the current data sets fit.
        self.axes.relim()
        self.axes.autoscale_view()
        # Rotate each tick mark
        xaxis = self.axes.xaxis
        ticksMajor = xaxis.get_ticklabels()
        ticksMinor = xaxis.get_ticklabels(minor=True)
        for tick in ticksMajor + ticksMinor:
            tick.set_rotation(90)
        # Put each series label at the far right of the axes.
        xMax = xaxis.get_view_interval()[1]
        for label in self.labels.values():
            label.set_x(xMax)

        # Update the canvas.
        self.canvas.draw()
        self.canvas.flush_events()

        
    def toggleShowKey(self, key):
        """Toggle the state of an entry in showKeys."""
        if self.showKeys[key] and self.showKeys.values().count(True) == 1:
            # This is the only key set to True. Do not change it.
            return
        self.showKeys[key] = not self.showKeys[key]
        

def makeWindow(parent):
    """Create the ValueLogger window instance and associated objects."""
    # The ValueLoggerWindow instance.
    global window
    window = ValueLoggerWindow(parent)