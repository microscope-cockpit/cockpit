#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
## Copyright (C) 2018 David Pinto <nicholas.hall@dtc.ox.ac.uk>
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


import cockpit.util.Mrc
import cockpit.util.datadoc
import cockpit.util.userConfig

from .structuredIllumination import *

import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = '2D SIM Flux'


## This class handles SI experiments.
class SIMFluxExperiment2D(SIExperiment):
    pass

EXPERIMENT_CLASS = SIMFluxExperiment2D

## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)

        self.configKey = configKey
        self.allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        self.settings = self.loadSettings()

        sizer = wx.BoxSizer(wx.VERTICAL)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.numPhases = guiUtils.addLabeledInput(self,
                                                  rowSizer, label="Number of phases",
                                                  helperString="How many phases do you want?")
        self.numPhases.SetValue(str(self.settings['numPhases']))
        sizer.Add(rowSizer)

        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.numAngles = guiUtils.addLabeledInput(self,
                                                  rowSizer, label="Number of angles",
                                                  helperString="How many angles do you want?")
        self.numAngles.SetValue(str(self.settings['numAngles']))
        sizer.Add(rowSizer)

        text = wx.StaticText(self, -1, "Exposure bleach compensation (%):")
        rowSizer.Add(text, 0, wx.ALL, 5)
        ## Ordered list of bleach compensation percentages.
        self.bleachCompensations, subSizer = guiUtils.makeLightsControls(
                self,
                [str(l.name) for l in self.allLights],
                self.settings['bleachCompensations'])
        rowSizer.Add(subSizer)
        sizer.Add(rowSizer)
        # Now a row for the collection order.
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.siCollectionOrder = guiUtils.addLabeledInput(self,
                rowSizer, label = "Collection order",
                control = wx.Choice(self, choices = sorted(COLLECTION_ORDERS.keys())),
                helperString = "What order to change the angle, phase, and Z step of the experiment. E.g. for \"Angle, Phase, Z\" Angle will change most slowly and Z will change fastest.")
        self.siCollectionOrder.SetSelection(self.settings['siCollectionOrder'])
        sizer.Add(rowSizer)
        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['numAngles'] = int(self.numAngles.GetValue())
        params['numPhases'] = int(self.numPhases.GetValue())
        params['collectionOrder'] = self.siCollectionOrder.GetStringSelection()
        params['angleHandler'] = depot.getHandlerWithName('SI angle')
        params['phaseHandler'] = depot.getHandlerWithName('SI phase')
        params['polarizerHandler'] = depot.getHandlerWithName('SI polarizer')
        params['slmHandler'] = depot.getHandler('slm', depot.EXECUTOR)
        compensations = {}
        for i, light in enumerate(self.allLights):
            val = guiUtils.tryParseNum(self.bleachCompensations[i], float)
            if val:
                # Convert from percentage to multiplier
                compensations[light] = .01 * float(val)
            else:
                compensations[light] = 0
        params['bleachCompensations'] = compensations
        return params


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        result = cockpit.util.userConfig.getValue(
                self.configKey + EXPERIMENT_CLASS.__name__,
                default = {
                    'numAngles': 2,
                    'numPhases': 50,
                    'bleachCompensations': ['' for l in self.allLights],
                    'siCollectionOrder': 0,
                }
        )
        if len(result['bleachCompensations']) != len(self.allLights):
            # Number of light sources has changed; invalidate the config.
            result['bleachCompensations'] = ['' for light in self.allLights]
        return result


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'numAngles': self.numAngles.GetValue(),
                'numPhases': self.numPhases.GetValue(),
                'bleachCompensations': [c.GetValue() for c in self.bleachCompensations],
                'siCollectionOrder': self.siCollectionOrder.GetSelection(),
        }


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        cockpit.util.userConfig.setValue(
                self.configKey + EXPERIMENT_CLASS.__name__, settings
        )