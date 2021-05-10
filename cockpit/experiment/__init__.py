#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

"""Experiments plans.

This package contains the code needed to run experiments.  Setup of
experiments is done in the :mod:``cockpit.gui.dialogs.experiment``
package, but that code ultimately just creates an ``Experiment``
subclass (e.g. ``ZStackExperiment``) with appropriate parameters.

Each ``Experiment`` subclass is responsible for registering itself in
``experimentRegistry`` so that the GUI modules know what experiments
are available.  Some of its modules are:

- :mod:`cockpit.experiment.actionTable`: describe the sequence of
  actions that take place as part of the experiment.

- :mod:`cockpit.experiment.dataSaver`: handles incoming image data,
  saving it to disk as it comes in.

- :mod:`cockpit.experiment.experiment`: base ``Experiment`` class that
  all other experiments subclass from.  Never used directly on its
  own.  The ``experiment.lastExperiment`` value holds the last class
  instance that was used to run an experiment, which can be useful for
  debugging.

"""
