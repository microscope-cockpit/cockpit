#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
## Copyright (C) 2023 Ian Dobbie ian.dobbie@jhu.edu
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

from cockpit.handlers import deviceHandler
from cockpit import depot
import cockpit.gui
import cockpit.gui.device
import wx
import cockpit.util.threads

class DigitalIOHandler(deviceHandler.DeviceHandler):
    """A handler for Digital IO devcies."""
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        super().__init__(name, groupName, isEligibleForExperiments,
                         callbacks, depot.DIO)
        self.isEnabled = False
                
    @property
    def paths(self):
        return self.callbacks['getPaths']()
        
    def onSaveSettings(self):
        paths={}
        for key in self.pathNameToButton.keys():
            paths[key]=int(self.pathNameToButton[key].GetValue())
        outputs=list(map(int,self.callbacks['getOutputs']()))
        IOstate = [self.callbacks['getIOstate'](i)
                   for i in range(len(outputs))]
        return [paths,outputs,IOstate]

    def onLoadSettings(self, settings):
        (paths,outputs,IOstate)=settings
        for key in paths.keys():
            self.pathNameToButton[key].SetValue(paths[key])
        for i,state in enumerate(IOstate):
            #proabbyl safer not to change IO state here
            #self.callbacks['setIOstate'](i,state)
            if state:
                self.callbacks['write line'](i,outputs[i])
            

    def setEnabled(self, shouldEnable = True):
        try:
            self.isEnabled = self.callbacks['enable'](shouldEnable)
        except:
            self.isEnabled = False
            raise
        if self.isEnabled != shouldEnable:
            raise Exception("Problem enabling device with handler %s" % self)

    ## Return self.isEnabled.
    def getIsEnabled(self):
        return self.isEnabled
    

       ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        enablebutton=cockpit.gui.device.EnableButton(self.panel,deviceHandler=self)
        sizer.Add(enablebutton,1,wx.EXPAND)
        self.pathNameToButton={}
        for key in self.paths.keys():
            button = wx.ToggleButton(self.panel, wx.ID_ANY)
            button.SetLabel(key)
            button.Bind(wx.EVT_TOGGLEBUTTON,
                        lambda evt,b=button: self.togglePaths(b))
            sizer.Add(button, 1, wx.EXPAND)
            self.pathNameToButton[key]=button
        self.panel.SetSizerAndFit(sizer)
        return self.panel

    def togglePaths(self,button):
        path=button.Label
        if button.GetValue():
            #button is active so set the relevant DIO lines
            #take settings for this path
            settings=self.paths[path]
            #loop throught DIO settings.
            for object in settings[0].keys():
                labels=self.callbacks['get labels']()
                line=labels.index(object)
                #loop through settings and set each named object to that state.
                self.callbacks['write line'](line, settings[0][object])
#                print(path,self.callbacks['getOutputs']())
            #Need some way to define exclusive and non-exclusive paths
            #assume they are exclusive for now.
            otherbuttons=settings[1]
            for key in otherbuttons.keys():
                self.pathNameToButton[key].SetValue(otherbuttons[key])

    @cockpit.util.threads.callInMainThread
    def updateAfterChange(self,*args):
#        # Accept *args so that can be called directly as a Pyro callback
#        # or an event handler.
        pass
#        # need to update display if active.
#self.


def finalizeInitialization(self):
        self.updateAfterChange()
