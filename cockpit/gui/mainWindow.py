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


## This module creates the primary window. This window houses widgets to 
# control the most important hardware elements.

from __future__ import absolute_import

import json
import wx
import os.path

from cockpit import depot
from .dialogs.experiment import multiSiteExperiment
from .dialogs.experiment import singleSiteExperiment
from cockpit import events
import cockpit.experiment.experiment
from . import fileViewerWindow
import cockpit.interfaces.imager
from . import joystick
from . import keyboard
from . import toggleButton
import cockpit.util.files
import cockpit.util.userConfig
from . import viewFileDropTarget
from cockpit.gui.device import OptionButtons
from cockpit.gui import mainPanels


from six import iteritems

## Window singleton
window = None

## Max width of rows of UI widgets.
# This number is chosen to match the width of the Macro Stage view.
MAX_WIDTH = 850
ROW_SPACER = 12
COL_SPACER = 8



class MainWindow(wx.Frame):
    ## Construct the Window. We're only responsible for setting up the 
    # user interface; we assume that the devices have already been initialized.
    def __init__(self):
        wx.Frame.__init__(self, parent = None, title = "Cockpit")
        # Find out what devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)

        ## Maps LightSource handlers to their associated panels of controls.
        self.lightToPanel = dict()
        ##objects to store paths and button names
        self.pathList = ['New...', 'Update','Load...', 'Save...']
        self.paths=dict()
        self.currentPath = None

        # Construct the UI.
        # Sizer for all controls. We'll split them into bottom half (light
        # sources) and top half (everything else).
        self.Sizer = wx.BoxSizer(wx.VERTICAL)

        # Panel for holding the non-lightsource controls.
        topPanel = wx.Panel(self)
        topPanel.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        self.topPanel=topPanel
        topSizer = wx.BoxSizer(wx.VERTICAL)
 

        # A row of buttons for various actions we know we can take.
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        abortButton = toggleButton.ToggleButton(textSize = 16,
                label = "\nABORT", size = (120, 80), parent = topPanel,
                inactiveColor = wx.RED)
        abortButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: events.publish('user abort'))
        buttonSizer.Add(abortButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Single-site\nExperiment", size = (120, 80), 
                parent = topPanel)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: singleSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Multi-site\nExperiment", size = (120, 80),
                parent = topPanel)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: multiSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        viewFileButton = toggleButton.ToggleButton(textSize = 12,
                label = "View last\nfile", size = (120, 80),
                parent = topPanel)
        viewFileButton.Bind(wx.EVT_LEFT_DOWN,
                self.onViewLastFile)
        buttonSizer.Add(viewFileButton)
        self.videoButton = toggleButton.ToggleButton(textSize = 12,
                label = "Video mode", size = (120, 80), parent = topPanel)
        self.videoButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: cockpit.interfaces.imager.videoMode())
        buttonSizer.Add(self.videoButton)
        self.pathButton =  OptionButtons(parent= topPanel,size=(120, 80))
        
        self.pathButton.setOptions (map(lambda name: (name,
                                                       lambda n=name:
                                                       self.setPath(n)),
                                         self.pathList))
        self.pathButton.mainButton.SetLabel(text='Path')
        buttonSizer.Add(self.pathButton)
        snapButton = toggleButton.ToggleButton(textSize = 12,
                label = "Snap",
                size = (120, 80), parent = topPanel)
        snapButton.Bind(wx.EVT_LEFT_DOWN, self.OnSnapButton)
        buttonSizer.Add(snapButton)

        topSizer.Add(buttonSizer)
        topSizer.AddSpacer(ROW_SPACER)

        # Make UIs for any other handlers / devices and insert them into
        # our window, if possible.
        # Light power things will be handled later.
        lightPowerThings = depot.getHandlersOfType(depot.LIGHT_POWER)
        lightPowerThings.sort(key = lambda l: l.wavelength)
        # Camera UIs are drawn seperately. Currently, they are drawn first,
        # but this separation may make it easier to implement cameras in
        # ordered slots, giving the user control over exposure order.
        cameraThings = depot.getHandlersOfType(depot.CAMERA)
        # Ignore anything that is handled specially.
        ignoreThings = lightToggles + lightPowerThings
        ignoreThings += cameraThings
        # Remove ignoreThings from the full list of devices.
        otherThings = list(depot.getAllDevices())
        otherThings.sort(key = lambda d: d.__class__.__name__)
        otherThings.extend(depot.getAllHandlers())
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)

        rowSizer.Add(mainPanels.ObjectiveControls(self.topPanel))
        rowSizer.AddSpacer(COL_SPACER)

        hs = depot.getHandlersOfType(depot.OBJECTIVE)
        ignoreThings.extend(hs)
        # Make the UI elements for the cameras.
        rowSizer.Add(mainPanels.CameraControlsPanel(self.topPanel))

        lightfilters = sorted(depot.getHandlersOfType(depot.LIGHT_FILTER))
        ignoreThings.extend(lightfilters)

        rowSizer.Add(mainPanels.FilterControls(self.topPanel), flag=wx.EXPAND)

        # Make the UI elements for eveything else.
        for thing in ignoreThings:
            if thing in otherThings:
                otherThings.remove(thing)
        for thing in sorted(otherThings):
            if depot.getHandler(thing, depot.CAMERA):
                # Camera UIs already drawn.
                continue
            item = thing.makeUI(topPanel)
            if item is not None:
                # Add it to the main controls display.
                if item.GetMinSize()[0] + rowSizer.GetMinSize()[0] > MAX_WIDTH:
                    # Start a new row, because the old one would be too
                    # wide to accommodate the item.
                    topSizer.Add(rowSizer, 1, wx.EXPAND)
                    rowSizer = wx.BoxSizer(wx.HORIZONTAL)
                if rowSizer.GetChildren():
                    # Add a spacer.
                    rowSizer.AddSpacer(COL_SPACER)
                rowSizer.Add(item)

        topSizer.Add(rowSizer)

        topPanel.SetSizerAndFit(topSizer)

        self.Sizer.Add(topPanel)
        self.Sizer.AddSpacer(ROW_SPACER)

        ## Panel for holding light sources.
        self.Sizer.Add(mainPanels.LightControlsPanel(self))

        # Ensure we use our full width if possible.
        size = self.Sizer.GetMinSize()
        if size[0] < MAX_WIDTH:
            self.Sizer.SetMinSize((MAX_WIDTH, size[1]))
        
        self.SetSizerAndFit(self.Sizer)

        keyboard.setKeyboardHandlers(self)
        self.joystick = joystick.Joystick(self)
            
        self.SetDropTarget(viewFileDropTarget.ViewFileDropTarget(self))
        self.Bind(wx.EVT_CLOSE, self.onClose)
        # Show the list of windows on right-click.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: keyboard.martialWindows(self))
        events.subscribe('video mode toggle', self.onVideoMode)


    ## Do any necessary program-shutdown events here instead of in the App's
    # OnExit, since in that function all of the WX objects have been destroyed
    # already.
    def onClose(self, event):
        events.publish('program exit')
        event.Skip()

    def OnSnapButton(self, evt):
        imager = cockpit.interfaces.imager.imager
        if len(imager.activeCameras):
            imager.takeImage()
        else:
            message = ('There are no active cameras to take an image.'
                       ' Turn one of the camera "on" first.')
            wx.MessageBox(message, caption='No cameras active', parent=self)


    ## Video mode has been turned on/off; update our button background.
    def onVideoMode(self, isEnabled):
        self.videoButton.setActive(isEnabled)


    ## User clicked the "view last file" button; open the last experiment's
    # file in an image viewer. A bit tricky when there's multiple files 
    # generated due to the splitting logic. We just view the first one in
    # that case.
    def onViewLastFile(self, event = None):
        filenames = cockpit.experiment.experiment.getLastFilenames()
        if filenames:
            window = fileViewerWindow.FileViewer(filenames[0], self)
            if len(filenames) > 1:
                print ("Opening first of %d files. Others can be viewed by dragging them from the filesystem onto the main window of the Cockpit." % len(filenames))


    ##user defined modes which include cameras and lasers active,
    ##filter whieels etc...
    def setPath(self, name):
        #store current path to text file
        if name == 'Save...':
            self.onSaveExposureSettings(self.currentPath)
        #load stored path
        elif name == 'Load...':
            self.onLoadExposureSettings()
        #update settings for current path
        elif name == 'Update' and self.currentPath != None:
            events.publish('save exposure settings',
                           self.paths[self.currentPath])
            self.pathButton.setOption(self.currentPath)
        #create newe stored path with current settings.
        elif name == 'New...':
            self.createNewPath()
        else:
            events.publish('load exposure settings', self.paths[name])
            self.currentPath = name
            self.pathButton.setOption(name)

    def createNewPath(self):
        #get name for new mode
        # abuse get value dialog which will also return a string. 
        pathName = cockpit.gui.dialogs.getNumberDialog.getNumberFromUser(
            parent=self.topPanel, default='', title='New Path Name',
            prompt='Name', atMouse=True)
        if not pathName:
            #None or empty string
            return()
        if pathName in self.paths :
            events.publish('save exposure settings',
                           self.paths[pathName])
            self.pathButton.setOption(pathName)
            return()
        self.paths[pathName]=dict()
        self.pathList.append(pathName)
        #publish an event to populate mode settings.
        events.publish('save exposure settings', self.paths[pathName])
        #update button entries.
        self.pathButton.setOptions(map(lambda name: (name,
                                                       lambda n=name:
                                                       self.setPath(n)),
                                         self.pathList))
        #and set button value. 
        self.pathButton.setOption(pathName)
        self.currentPath = pathName

                       
                
    ## User wants to save the current exposure settings; get a file path
    # to save to, collect exposure information via an event, and save it.
    def onSaveExposureSettings(self, name, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                               defaultFile=name+'.txt',
                message = "Please select where to save the settings.",
                defaultDir = cockpit.util.files.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            self.pathButton.setOption(name)
            return
        settings = dict()
        events.publish('save exposure settings', settings)
        handle = open(dialog.GetPath(), 'w')
        handle.write(json.dumps(settings))
        handle.close()
        self.pathButton.setOption(name)

    
    ## User wants to load an old set of exposure settings; get a file path
    # to load from, and publish an event with the data.
    def onLoadExposureSettings(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = "Please select the settings file to load.",
                defaultDir = cockpit.util.files.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            self.pathButton.setOption(self.currentPath)
            return
        handle = open(dialog.GetPath(), 'r')
        modeName=os.path.splitext(os.path.basename(handle.name))[0]
        #get name for new mode
        # abuse get value dialog which will also return a string. 
        name = cockpit.gui.dialogs.getNumberDialog.getNumberFromUser(
            parent=self.topPanel, default=modeName, title='New Path Name',
            prompt='Name')
        if name not in self.paths:
            self.pathList.append(name)
        self.paths[name] = json.loads('\n'.join(handle.readlines()))
        handle.close()
        events.publish('load exposure settings', self.paths[name])
        #update button list
        self.pathButton.setOptions(map(lambda name: (name,
                                                       lambda n=name:
                                                       self.setPath(n)),
                                         self.pathList))
        #and set button value. 
        self.pathButton.setOption(name)
        self.currentPath = name
       

        # If we're using the listbox approach to show/hide light controls,
        # then make sure all enabled lights are shown and vice versa.
        if self.lightList is not None:
            for i, name in enumerate(self.lightList.GetItems()):
                handler = depot.getHandlerWithName(name)
                self.lightList.SetStringSelection(name, handler.getIsEnabled())
            self.onLightSelect()


    ## User selected/deselected a light source from self.lightList; determine
    # which light panels should be shown/hidden.
    def onLightSelect(self, event = None):
        selectionIndices = self.lightList.GetSelections()
        items = self.lightList.GetItems()
        for light, panel in iteritems(self.lightToPanel):
            panel.Show(items.index(light.name) in selectionIndices)
        # Fix display. We need to redisplay ourselves as well in case the
        # newly-displayed lights are extending off the edge of the window.
        self.bottomPanel.SetSizerAndFit(self.bottomPanel.GetSizer())
        self.SetSizerAndFit(self.GetSizer())



## Create the window.
def makeWindow():
    global window
    window = MainWindow()
    window.Show()
    return window
