#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
## Copyright (C) 2019 Nicholas Hall <nicholas.hall@dtc.ox.ac.uk>
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

from cockpit.gui import guiUtils
from cockpit.experiment import structuredIllumination

import wx


EXPERIMENT_NAME = 'SIM Flux'

EXPERIMENT_CLASS = structuredIllumination.SIExperiment


class ExperimentUI(structuredIllumination.BaseSIMExperimentUI):
    _CONFIG_KEY_SUFFIX = 'SIMFluxExperimentSettings'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.numPhases = guiUtils.addLabeledInput(self, rowSizer,
                                                  label="Number of phases",
                                                  helperString="How many phases do you want?")
        self.numPhases.SetValue(str(self.settings['numPhases']))
        self.Sizer.Insert(0, rowSizer)

        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.numAngles = guiUtils.addLabeledInput(self, rowSizer,
                                                  label="Number of angles",
                                                  helperString="How many angles do you want?")
        self.numAngles.SetValue(str(self.settings['numAngles']))
        self.Sizer.Insert(1, rowSizer)

        self.Sizer.SetSizeHints(self)

    def augmentParams(self, params):
        params = super().augmentParams(params)
        params['numAngles'] = int(self.numAngles.GetValue())
        params['numPhases'] = int(self.numPhases.GetValue())
        return params

    def _getDefaultSettings(self):
        default = super()._getDefaultSettings()
        default.update({
            'numAngles': 2,
            'numPhases': 50,
        })
        return default

    def getSettingsDict(self):
        all_settings = super().getSettingsDict()
        all_settings.update({
            'numAngles': self.numAngles.GetValue(),
            'numPhases': self.numPhases.GetValue(),
        })
        return all_settings
