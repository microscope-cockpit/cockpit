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


from cockpit.devices import device
from cockpit.util import valueLogger
from cockpit import events
import collections
import Pyro4
import wx
import cockpit.gui.device

from cockpit.handlers.objective import ObjectiveHandler

## TODO: Clean up code.

class RaspberryPi(device.Device):
    def __init__(self, name, config):
        # self.ipAddress and self.port set by device.Device.__init__
        super().__init__(name, config)
        linestring = config.get('lines')
        self.lines = linestring.split(',')
        paths_linesString = config.get('paths')
        self.excitation=[]
        self.excitationMaps=[]
        self.objective=[]
        self.objectiveMaps=[]

        for path in (paths_linesString.split(';')):
            parts = path.split(':')
            if(parts[0]=='objective'):
                self.objective.append(parts[1])
                self.objectiveMaps.append(parts[2])
            elif (parts[0]=='excitation'):
                self.excitation.append(parts[1])
                self.excitationMaps.append(parts[2])

        self.RPiConnection = None
        ## util.connection.Connection for the temperature sensors.

        ## Maps light modes to the mirror settings for those modes, as a list
        #IMD 20140806
        #map paths to flips. 
        self.modeToFlips = collections.OrderedDict()
        for i in range(len(self.excitation)):
            self.modeToFlips[self.excitation[i]] = []
            for flips in self.excitationMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.modeToFlips[self.excitation[i]].append(flipsInt)        
        #map objectives to flips. 
        self.objectiveToFlips = collections.OrderedDict()
        for i in range(len(self.objective)):
            self.objectiveToFlips[self.objective[i]] = []
            for flips in self.objectiveMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.objectiveToFlips[self.objective[i]].append(flipsInt)
                
        self.lightPathButtons = []
        ## Current light path mode.
        self.curExMode = None

        ## Connect to the remote program, and set widefield mode.
    def initialize(self):
        self.RPiConnection = Pyro4.Proxy('PYRO:%s@%s:%d' % ('pi', self.ipAddress, self.port))
        ## Log temperatures
        self.logger = valueLogger.PollingLogger(self.name, 15,
                                                self.RPiConnection.get_temperature)

    def onExit(self) -> None:
        if self.RPiConnection is not None:
            self.RPiConnection._pyroRelease()
        super().onExit()

    ## Try to switch to widefield mode.
    def finalizeInitialization(self):
        #set the first excitation mode as the inital state.
        self.setExMode(self.excitation[1])
        #Subscribe to objective change to map new detector path to new pixel sizes via fake objective
        events.subscribe('objective change', self.onObjectiveChange)

    
    ## Generate a column of buttons for setting the light path. Make a window
    # that plots our temperature data.
    def makeUI(self, parent):
        rowSizer=wx.BoxSizer(wx.HORIZONTAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = cockpit.gui.device.Label(parent, -1, "Excitation path:")
        sizer.Add(label)
        for mode in self.excitation:
            button = wx.ToggleButton(parent, wx.ID_ANY, mode)
            # Respond to clicks on the button.
            button.Bind(wx.EVT_TOGGLEBUTTON, lambda event, mode = mode: self.setExMode(mode))
            sizer.Add(button, 1, wx.EXPAND)
            self.lightPathButtons.append(button)
            if mode == self.curExMode:
                button.SetValue(True)
        rowSizer.Add(sizer)
        return rowSizer


    ## Set the light path to the specified mode.
    def setExMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.lightPathButtons:
            button.SetValue(button.GetLabel() == mode)
        self.curExMode = mode


    ## Flip a mirror down and then up, to ensure that it's in the position
    # we want.
    def flipDownUp(self, index, isUp):
        self.RPiConnection.flipDownUp(index, int(isUp))


    def onObjectiveChange(self, handler: ObjectiveHandler) -> None:
        for flips in self.objectiveToFlips[handler.name]:
            self.flipDownUp(flips[0], flips[1])


    ## Debugging function: display a debug window.
    def showDebugWindow(self):
        piOutputWindow(self, parent=wx.GetApp().GetTopWindow()).Show()


## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class piOutputWindow(wx.Frame):
    def __init__(self, piDIO, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        ## piDevice instance.
        self.pi = piDIO
        # Contains all widgets.
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 4, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        # Set up the digital lineout buttons.
        for i in range(len(piDIO.lines)) :
            button = wx.ToggleButton(panel, wx.ID_ANY, str(piDIO.lines[i]))
            button.Bind(wx.EVT_TOGGLEBUTTON, lambda evt: self.toggle())
            buttonSizer.Add(button, 1, wx.EXPAND)
            self.buttonToLine[button] = i
        mainSizer.Add(buttonSizer)

        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())


    ## One of our buttons was clicked; update the DSP's output.
    def toggle(self):
        output = 0
        for button, line in self.buttonToLine.items():
            if button.GetValue():
                self.pi.RPiConnection.flipDownUp(line, 1)
            else:
                self.pi.RPiConnection.flipDownUp(line, 0)
