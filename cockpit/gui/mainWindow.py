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
import cockpit.util.user
import cockpit.util.userConfig
from . import viewFileDropTarget
from cockpit.gui.device import OptionButtons


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
        wx.Frame.__init__(self, parent = None, title = "Cockpit program")
        # Find out what devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        lightToggles = sorted(lightToggles, key = lambda l: float(l.wavelength))
        # Set of objects that are in the same group as any light toggle.
        # lightAssociates = set()
        # for toggle in lightToggles:
        #     lightAssociates.update(depot.getHandlersInGroup(toggle.groupName))

        ## Maps LightSource handlers to their associated panels of controls.
        self.lightToPanel = dict()
        ##objects to store paths and button names
        self.pathList = ['New...', 'Update','Load...', 'Save...']
        self.paths=dict()
        self.currentPath = None

        # Construct the UI.
        # Sizer for all controls. We'll split them into bottom half (light
        # sources) and top half (everything else).
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        # Panel for holding the non-lightsource controls.
        topPanel = wx.Panel(self)
        topPanel.SetBackgroundColour((170, 170, 170))
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
        snapButton.Bind(wx.EVT_LEFT_DOWN,
                        lambda event: cockpit.interfaces.imager.takeImage())
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
        #ignoreThings = lightToggles + list(lightAssociates) + lightPowerThings
        ignoreThings = lightToggles + lightPowerThings
        ignoreThings += cameraThings
        # Remove ignoreThings from the full list of devices.
        otherThings = list(depot.getAllDevices())
        otherThings.sort(key = lambda d: d.__class__.__name__)
        otherThings.extend(depot.getAllHandlers())
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        hs = depot.getHandlersOfType(depot.OBJECTIVE)
        for h in hs:
            rowSizer.Add(h.makeUI(topPanel))
            rowSizer.AddSpacer(COL_SPACER)
        ignoreThings.extend(hs)
        # Make the UI elements for the cameras.
        for camera in sorted(cameraThings):
            # Clear cameraUI so we don't use previous value.
            cameraUI = None
            # See if the camera has a function to make UI elements.
            uiFunc = camera.makeUI
            # If there is a UI function, evaluate it.
            if uiFunc:
                cameraUI = uiFunc(topPanel)
            # uiFunc should return a panel.
            if cameraUI:
                rowSizer.Add(cameraUI)
                rowSizer.AddSpacer(COL_SPACER)
        # Make UI elements for filters.
        hs = sorted(depot.getHandlersOfType(depot.LIGHT_FILTER))
        for i, h in enumerate(hs):
            if i%2 == 0:
                s = wx.BoxSizer(wx.VERTICAL)
                rowSizer.Add(s)
                rowSizer.AddSpacer(COL_SPACER)
            else:
                s.AddSpacer(ROW_SPACER)
            s.Add(h.makeUI(topPanel))
        rowSizer.AddSpacer(COL_SPACER)
        ignoreThings.extend(hs)
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

        topSizer.Add(rowSizer, 1)

        topPanel.SetSizerAndFit(topSizer)
        mainSizer.Add(topPanel)
        mainSizer.AddSpacer(ROW_SPACER)

        ## Panel for holding light sources.
        self.bottomPanel = wx.Panel(self)
        self.bottomPanel.SetBackgroundColour((170, 170, 170))
        bottomSizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self.bottomPanel, -1, "Illumination controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        bottomSizer.Add(label)
        lightSizer = wx.BoxSizer(wx.HORIZONTAL)
        # If we have a lot (more than 7) of light sources, then we hide
        # light sources by default and provide a listbox to let people show
        # only the ones they need.
        ## wx.ListBox of all lights, assuming we're using this UI modus.
        self.lightList = None
        if len(lightToggles) > 7:
            haveDynamicLightDisplay = True
            self.lightList = wx.ListBox(self.bottomPanel, -1,
                    size = (-1, 200), style = wx.LB_MULTIPLE,
                    choices = [light.name for light in lightToggles])
            self.lightList.Bind(wx.EVT_LISTBOX, self.onLightSelect)
            lightSizer.Add(self.lightList)
        # Construct the lightsource widgets. One column per light source.
        # Associated handlers on top, then then enable/disable toggle for the
        # actual light source, then exposure time, then any widgets that the
        # device code feels like adding.
        for light in lightToggles:
            lightPanel = wx.Panel(self.bottomPanel)
            # Enable double-buffering so StaticText labels don't flicker.
            lightPanel.SetDoubleBuffered(True)
            self.lightToPanel[light] = lightPanel
            columnSizer = wx.BoxSizer(wx.VERTICAL)
            haveOtherHandler = False
            for otherHandler in depot.getHandlersInGroup(light.groupName):
                if otherHandler is not light:
                    columnSizer.Add(otherHandler.makeUI(lightPanel))
                    haveOtherHandler = True
                    break
            if not haveOtherHandler:
                # Put a spacer in so this widget has the same vertical size.
                columnSizer.Add((-1, 1), 1, wx.EXPAND)
            lightUI = light.makeUI(lightPanel)
            columnSizer.Add(lightUI)
            events.publish('create light controls', lightPanel,
                    columnSizer, light)
            lightPanel.SetSizerAndFit(columnSizer)
            if self.lightList is not None:
                # Hide the panel by default; it will be shown only when
                # selected in the listbox.
                lightPanel.Hide()
            # Hack: the ambient light source goes first in the list.
            if 'Ambient' in light.groupName:
                lightSizer.Insert(0, lightPanel, 1, wx.EXPAND | wx.VERTICAL)
            else:
                lightSizer.Add(lightPanel, 1, wx.EXPAND | wx.VERTICAL)
        bottomSizer.Add(lightSizer)

        self.bottomPanel.SetSizerAndFit(bottomSizer)
        mainSizer.Add(self.bottomPanel)

        # Ensure we use our full width if possible.
        size = mainSizer.GetMinSize()
        if size[0] < MAX_WIDTH:
            mainSizer.SetMinSize((MAX_WIDTH, size[1]))
        
        self.SetSizerAndFit(mainSizer)

        keyboard.setKeyboardHandlers(self)
        self.joystick = joystick.Joystick(self)
        self.SetDropTarget(viewFileDropTarget.ViewFileDropTarget(self))
        self.Bind(wx.EVT_MOVE, self.onMove)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        # Show the list of windows on right-click.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: keyboard.martialWindows(self))
        events.subscribe('user login', self.onUserLogin)
        events.subscribe('video mode toggle', self.onVideoMode)


    ## Save the position of our window. For all other windows, this is handled
    # by cockpit.util.user.logout, but by the time that function gets called, we've
    # already been destroyed.
    def onMove(self, event):
        cockpit.util.userConfig.setValue('mainWindowPosition', tuple(self.GetPosition()))


    ## Do any necessary program-shutdown events here instead of in the App's
    # OnExit, since in that function all of the WX objects have been destroyed
    # already.
    def onClose(self, event):
        events.publish('program exit')
        event.Skip()


    ## User logged in; update our title.
    def onUserLogin(self, username):
        self.SetTitle("Cockpit program (currently logged in as %s)" % username)


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
                defaultDir = cockpit.util.user.getUserSaveDir())
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
                defaultDir = cockpit.util.user.getUserSaveDir())
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
