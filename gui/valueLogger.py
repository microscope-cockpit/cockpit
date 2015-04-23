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
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import threading
import time
import wx


class ValueLoggerWindow(wx.Frame):
    def __init__(self, parent, title='value logger'):
        super(ValueLoggerWindow, self).__init__(
                parent, -1, title,
                style = wx.CAPTION | wx.RESIZE_BORDER)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.panel = ValueLoggerPanel(self)
        self.Show()


    def onClose(self, *args):
        window = None
        self.panel.Destroy()
        self.Destroy()


class ValueLoggerPanel(wx.Panel):
    def __init__(self, parent):
        super(ValueLoggerPanel, self).__init__(parent)
        self.lines = {}
        self.figure = Figure()
        self.axes = self.figure.add_subplot(111)
        self.axes.set_position([0.1, 0.1, 0.6, 0.85])
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        self.SetSizerAndFit(self.sizer)
        events.subscribe("valuelogger update", self.draw)
        self.canvas.Bind(wx.EVT_RIGHT_DOWN, self.onRightMouse)


    def onRightMouse(self, *args):
        menu = wx.Menu()
        for i, (key, enabled) in enumerate(sorted(showKeys.items())):
            menu.Append(i, key, '', wx.ITEM_CHECK)
            menu.Check(i, enabled)
            wx.EVT_MENU(menu, i, lambda event, k=key:toggleShowKey(k))
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
                continue
            if not showKeys:
                showKeys[key] = True
            elif key not in showKeys:
                showKeys[key] = False

            line = self.lines.get(key, None)
            if showKeys[key]:
                if line:
                    line.set_data(dataTimes, series)
                elif len(series) > 0:
                    self.lines[key], = self.axes.plot(dataTimes, series)
            else:
                if line:
                    self.axes.lines.remove(line)
                    self.lines[key] = None
        self.axes.legend([k for k in showKeys if showKeys[k]], 
                         loc='center left', bbox_to_anchor=(1, 0.5),
                         prop={'size':11})
        self.axes.relim()
        self.axes.autoscale_view()
        self.canvas.draw()
        self.canvas.flush_events()
        

def toggleShowKey(key):
    showKeys[key] = not showKeys[key]


def makeWindow(parent):
    global window
    global showKeys
    window = ValueLoggerWindow(parent)
    showKeys = {}