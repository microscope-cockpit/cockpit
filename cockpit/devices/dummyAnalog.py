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

from cockpit import depot
from cockpit.devices import device
import re


class DummyAnalogDevice(device.Device):
    """A dummy analogue client device.

    An analogue client is some device that is driven by a voltage from
    an analogue source.  The analogue source device is responsible for
    setting output voltages and running sweeps.  Previously, handling
    of certain analogue devices was hard coded into executor devices,
    like the DSP, but this lacks flexibility.  Instead, we need some
    intermediate handler so that the control of the client devices is
    clearer in experiments.

    An analogue client:

    - registers itself with an analogue source
    - offers a GenericPositioner handler

    The GenericPositioner will appear in experiment ActionTables, but
    the analogue source will be responsible for executing those lines
    in the table.  Historically, there were to types of analogue
    devices used in experiments.

    1. those that the experiment moves through a continuous range,
       such as piezo devices;
    2. those that the experiment moves through indexed positions.

    In the latter case, indexed positions were often hard coded into
    the analogue *source device* code.  Again, this lacks flexibility,
    and thoroughly breaks an abstracted, modular device model.  Now,
    indexed positions are stored on the client device, and experiments
    will only ever move devices to positions within their continuous
    range - i.e., the experiment will look up positions from those
    stored on the device, and insert those into the action table
    rather than the index.

    """
    def __init__(self, name, config={}):
        super().__init__(name, config)

    def initialize(self):
        pass

    def getMovementTime(self, start, finish):
        return (abs(finish - start)*1e-6, 1e-6)

    def getHandlers(self):
        # Fetch analog configuration
        asource = self.config.get('analogsource', None)
        aline = self.config.get('analogline', None)
        gain = self.config.get('gain', 1)
        offset = self.config.get('offset', 0)
        # Fetch source handler and generate line handler.
        exe = depot.getHandler(asource, depot.EXECUTOR)
        h = exe.registerAnalog(self, aline, offset, gain, self.getMovementTime)
        # Add indexed positions if specified in config.
        positions = self.config.get('positions', None)
        if positions:
            h.positions = map(float, re.split('[;,]\s*', positions))
        return [h]
