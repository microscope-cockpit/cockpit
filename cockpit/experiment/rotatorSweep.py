#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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

from cockpit.experiment import actionTable
from cockpit import depot
from cockpit.experiment import experiment
from cockpit.gui import guiUtils
import cockpit.util

import decimal
import wx


## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'RotatorSweep'


## This class handles classic Z-stack experiments.
class RotatorSweepExperiment(experiment.Experiment):
    def __init__(self, polarizerHandler=None, settlingTime=0.1,
                 startV=0.0, maxV=10., vSteps=100, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.polarizerHandler = polarizerHandler
        self.settlingTime = settlingTime
        # Look up the rotator analogue line handler.
        self.lineHandler = polarizerHandler
        self.vRange = (startV, maxV, vSteps)
        vDelta = float(maxV - startV) / vSteps
        # Add voltage parameters to the metadata.
        self.metadata = 'Rotator start and delta: [%f, %f]' % (startV, vDelta)


    ## Create the ActionTable needed to run the experiment.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        vStart, vLessThan, vSteps = self.vRange
        dv = float(vLessThan - vStart) / float(vSteps)
        dt = decimal.Decimal(self.settlingTime)

        for step in range(vSteps):
            # Move to next polarization rotator voltage.
            vTarget = vStart + step * dv
            table.addAction(curTime, self.lineHandler, vTarget)
            curTime += dt
            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('.001')
            # Hold the rotator angle constant during the exposure.
            table.addAction(curTime, self.lineHandler, vTarget)
            # Advance time slightly so all actions are sorted (e.g. we
            # don't try to change angle and phase in the same timestep).
            curTime += dt

        return table


## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = RotatorSweepExperiment
from cockpit.gui.guiUtils import FLOATVALIDATOR, INTVALIDATOR

## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        super().__init__(parent = parent)
        self.configKey = configKey
        sizer = wx.GridSizer(2, 4, 1)
        ## Maps strings to TextCtrls describing how to configure
        # response curve experiments.
        self.settings = self.loadSettings()
        self.settlingTimeControl = guiUtils.addLabeledInput(
                                        self, sizer, label='settling time',
                                        defaultValue=self.settings['settlingTime'],)
        self.settlingTimeControl.SetValidator(FLOATVALIDATOR)

        self.vStepsControl = guiUtils.addLabeledInput(
                                        self, sizer, label='V steps',
                                        defaultValue=self.settings['vSteps'],)
        self.vStepsControl.SetValidator(INTVALIDATOR)

        self.startVControl = guiUtils.addLabeledInput(
                                        self, sizer, label='V start',
                                        defaultValue=self.settings['startV'],)
        self.startVControl.SetValidator(FLOATVALIDATOR)

        self.maxVControl = guiUtils.addLabeledInput(
                                        self, sizer, label='V max',
                                        defaultValue=self.settings['maxV'],)
        self.maxVControl.SetValidator(FLOATVALIDATOR)

        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['settlingTime'] = guiUtils.tryParseNum(self.settlingTimeControl, float)
        params['startV'] = guiUtils.tryParseNum(self.startVControl, float)
        params['maxV'] = guiUtils.tryParseNum(self.maxVControl, float)
        params['vSteps'] = guiUtils.tryParseNum(self.vStepsControl)
        params['polarizerHandler'] = depot.getHandlerWithName('SI polarizer')
        return params


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        return cockpit.util.userConfig.getValue(
                self.configKey + 'RotatorSweepExperimentSettings',
                default = {
                    'settlingTime': '0.1',
                    'startV' : '0.0',
                    'maxV': '10.0',
                    'vSteps': '100',
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return  {
                'settlingTime': self.settlingTimeControl.GetValue(),
                'startV': self.startVControl.GetValue(),
                'maxV': self.maxVControl.GetValue(),
                'vSteps': self.vStepsControl.GetValue(),}


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        cockpit.util.userConfig.setValue(
                self.configKey + 'RotatorSweepExperimentSettings',
                settings)
