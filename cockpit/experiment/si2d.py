#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

from cockpit.experiment import structuredIllumination


EXPERIMENT_NAME = '2D Structured Illumination'

EXPERIMENT_CLASS = structuredIllumination.SIExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(structuredIllumination.BaseSIMExperimentUI):
    _CONFIG_KEY_SUFFIX = 'SIExperiment2D'

    def augmentParams(self, params):
        params = super().augmentParams(params)
        params['numPhases'] = 3
        return params
