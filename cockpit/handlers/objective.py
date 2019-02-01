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


import wx

from cockpit import depot
from . import deviceHandler

from cockpit import events
import re

## This handler is responsible for tracking the current objective. 
class ObjectiveHandler(deviceHandler.DeviceHandler):
    ## \param nameToPixelSize A mapping of objective names to how many microns
    #         wide a pixel using that objective appears to be.
    # \param curObjective Currently-active objective.
    # \param callbacks
    # - setObjective(name, objectiveName): Set the current objective to the
    #   named one. This is an optional callback; if not provided, nothing is
    #   done.
    def __init__(self, name, groupName, nameToNA, nameToPixelSize, nameToTransform, nameToOffset, nameToColour, nameToLensID, curObjective,
            callbacks = {}):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, 
                False, {}, depot.OBJECTIVE)
        self.nameToNA = nameToNA
        self.nameToPixelSize = nameToPixelSize
        self.nameToTransform = nameToTransform
        self.nameToOffset = nameToOffset
        self.nameToColour = nameToColour
        self.nameToLensID = nameToLensID
        self.curObjective = curObjective
        self.callbacks = callbacks
        ## List of ToggleButtons, one per objective.
        self.buttons = []

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)

    @property
    def numObjectives(self):
        return len(self.nameToPixelSize)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.curObjective


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            self.changeObjective(settings[self.name])


    ## A list of objectives sorted by magnification.
    @property
    def sortedObjectives(self):
        def parseMag(name):
            m = re.search('[0-9.]+', name)
            if m is None:
                return None
            else:
                return float(m.group())
        return sorted(self.nameToPixelSize.keys(), key=parseMag)


    ## Generate a row of buttons, one for each possible objective.
    def makeUI(self, parent):
        from cockpit.gui.device import OptionButtons
        names = self.sortedObjectives
        frame = OptionButtons(parent, label="Objective")
        frame.Show()
        frame.setOptions(map(lambda name: (name,
                                           lambda n=name: self.changeObjective(n)), names))

        events.subscribe("objective change", lambda *a, **kw: frame.setOption(a[0]))
        return frame


    ## Let everyone know what the initial objective.
    def makeInitialPublications(self):
        self.changeObjective(self.curObjective)


    ## Let everyone know that the objective has been changed.
    def changeObjective(self, newName):
        if 'setObjective' in self.callbacks:
            self.callbacks['setObjective'](self.name, newName)
        self.curObjective = newName
        events.publish("objective change", newName, 
                pixelSize=self.nameToPixelSize[newName], 
                transform=self.nameToTransform[newName],
                offset=self.nameToOffset[newName])				


    ## Get the current pixel size.
    def getPixelSize(self):
        return self.nameToPixelSize[self.curObjective]
		
    ## Get the current pixel size.
    def getNA(self):
        return self.nameToNA[self.curObjective]

    ## Get the current offset.
    def getOffset(self):
        return self.nameToOffset[self.curObjective]

    ## Get Current lensID for file metadata.
    def getLensID(self):
        return self.nameToLensID[self.curObjective]

    ## Get Current lens colour.
    def getColour(self):
        return self.nameToColour[self.curObjective]
