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

from cockpit import events
import cockpit.util.userConfig
from cockpit.experiment import zStack

import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Stuttered Z-stack'


## This class handles experiments where we alter the rate at which we take
# stacks as a function of time. E.g. (each | represents a single volume):
# ||||   |   |   |   ||||   |   |   |   |||| ...
class StutteredZStackExperiment(zStack.ZStackExperiment):
    ## \param sampleRates A list of (interval, numReps) tuples indicating
    #         the amount of time in seconds between each rep, and the
    #         number of reps to perform at that rate. If we hit the end of
    #         the list before running out of reps, then we recommence from
    #         the beginning.
    def __init__(self, sampleRates, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sampleRates = sampleRates
        self.shouldAbort = False

        events.subscribe(events.USER_ABORT, self.onAbort)


    ## User aborted.
    def onAbort(self):
        self.shouldAbort = True

        
    ## Call Experiment.execute() repeatedly, while varying self.numReps and
    # self.repDuration so that we do the right sequence with the right 
    # timings. 
    def execute(self):
        # HACK: replace self.numReps since it's used in Experiment.execute(),
        # which we will be calling from within this function. We'll handle
        # reps more directly.
        trueReps = self.numReps
        numRepsPerformed = 0
        sequenceIndex = 0
        wasSuccessful = True
        while numRepsPerformed < trueReps:
            interval, numReps = self.sampleRates[sequenceIndex % len(self.sampleRates)]
            numReps = min(numReps, trueReps - numRepsPerformed)
            # Set these values so that Experiment.execute() can use them
            # safely.
            self.numReps = numReps
            self.repDuration = interval
            # Run a normal experiment.
            wasSuccessful = super().execute()
            sequenceIndex += 1
            numRepsPerformed += numReps
            if self.shouldAbort:
                return False
        return wasSuccessful



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = StutteredZStackExperiment
from cockpit.gui.guiUtils import FLOATVALIDATOR, INTVALIDATOR

class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        super().__init__(parent=parent)

        self.configKey = configKey
        ## List of (interval in seconds, number of reps) tuples
        # representing the rate at which we should image the
        # sample.
        self.sampleRates = []

        sizer = wx.FlexGridSizer(2, 6, 2, 2)
        sizer.Add((0, 0))
        sizer.Add((0, 0))
        sizer.Add(wx.StaticText(self, -1, 'Sampling sequence'))
        sizer.Add(wx.StaticText(self, -1, 'Interval (s)'))
        sizer.Add(wx.StaticText(self, -1, 'Reps'))
        sizer.Add((0, 0))
        # Commence second row.
        button = wx.Button(self, -1, 'Clear')
        button.Bind(wx.EVT_BUTTON, self.onClear)
        button.SetToolTip(wx.ToolTip("Remove all entries"))
        sizer.Add(button)

        button = wx.Button(self, -1, 'Delete last')
        button.Bind(wx.EVT_BUTTON, self.onDeleteLast)
        button.SetToolTip(wx.ToolTip("Remove the most recently-added entry"))
        sizer.Add(button)

        self.sequenceText = wx.TextCtrl(self, -1,
                size = (200, -1), style = wx.TE_READONLY)
        self.sequenceText.SetToolTip(wx.ToolTip("Displays the sequence of " +
                "sampling intervals and reps we will perform for this " +
                "experiment."))
        sizer.Add(self.sequenceText)

        self.interval = wx.TextCtrl(self, -1, size = (60, -1))
        self.interval.SetToolTip(wx.ToolTip("Amount of time, in seconds, that " +
                "passes between each rep for this portion of the experiment."))
        self.interval.SetValidator(FLOATVALIDATOR)
        self.interval.allowEmpty = True
        sizer.Add(self.interval)

        self.numReps = wx.TextCtrl(self, -1, size = (60, -1))
        self.numReps.SetToolTip(wx.ToolTip("Number of reps to perform at this " +
                "sampling interval."))
        self.numReps.SetValidator(INTVALIDATOR)
        self.numReps.allowEmpty = True
        sizer.Add(self.numReps)

        button = wx.Button(self, -1, 'Add')
        button.Bind(wx.EVT_BUTTON, self.onAdd)
        button.SetToolTip(wx.ToolTip("Add this (interval, reps) pair to the sequence."))
        sizer.Add(button)

        self.SetSizerAndFit(sizer)


    ## User clicked the "Clear" button; wipe out our current settings.
    def onClear(self, event = None):
        self.sampleRates = []
        self.setText()


    ## User clicked the "Delete last" button; remove the most recent setting.
    def onDeleteLast(self, event = None):
        self.sampleRates = self.sampleRates[:-1]
        self.setText()


    ## User clicked the "Add" button; add the new pair to our settings.
    def onAdd(self, event = None):
        interval = float(self.interval.GetValue())
        numReps = int(self.numReps.GetValue())
        self.sampleRates.append((interval, numReps))
        self.interval.SetValue('')
        self.numReps.SetValue('')
        self.setText()


    ## Update our text display of the settings.
    def setText(self):
        text = ', '.join(["(%.2f, %d)" % (i, n) for (i, n) in self.sampleRates])
        self.sequenceText.SetValue(text)


    def augmentParams(self, params, shouldSave = True):
        if shouldSave:
            self.saveSettings()
        params['sampleRates'] = self.getSampleRates()
        return params


    def loadSettings(self):
        return cockpit.util.userConfig.getValue(
                self.configKey + 'StutteredZStackSettings',
                default = [])


    def getSampleRates(self):
        return self.sampleRates


    def getSettingsDict(self):
        return self.augmentParams({}, shouldSave = False)


    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        cockpit.util.userConfig.setValue(
                self.configKey + 'StutteredZStackSettings', settings)


