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

from decimal import Decimal
from cockpit.devices.device import Device
from cockpit.interfaces.stageMover import AXIS_MAP
from cockpit.handlers import stagePositioner
from cockpit import depot


class SimplePiezo(Device):
    """A simple piezo axis.

    Sample config entry:

    .. code:: ini

        [zPiezo]                 # name
        type: cockpit.devices.stage.SimplePiezo        # this class
        analogSource: asource    # an analogue source device name
        analogLine: 0            # the line on the analogue source
        offset: 0                # analogue units offset in experiment units, e.g. um
        gain: 262.144            # unit conversion gain, e.g. ADU per um
        min: 0                   # min axis range in experimental units
        range: 250               # axis range in experimental units

    """
    _config_types = {
        # Min, max and range are ints to prevent crashes where ints are expected
        # in UI code. We should fix this to be able to use floats.
        'range': int,
        'min':   int,
        'max':   int,
        'stepmin': int,
        'offset': float,
        'gain': float,
    }

    def __init__(self, name, config):
        super(SimplePiezo, self).__init__(name, config)

    def getHandlers(self):
        asource = self.config.get('analogsource', None)
        aline = self.config.get('analogline', None)
        aHandler = depot.getHandler(asource, depot.EXECUTOR)
        if aHandler is None:
            raise Exception('No control source.')
        axis = AXIS_MAP[self.config.get('axis', 2)]
        offset = self.config.get('offset', 0)
        gain = self.config.get('gain', 1)
        posMin = self.config.get('min', None)
        posMax = self.config.get('max', None)
        posRange = self.config.get('range', None)
        haveMin, haveMax, haveRange = [v is not None for v in [posMin, posMax, posRange]]
        if haveMin and haveMax:
            pass
        elif (haveMin, haveMax, haveRange) == (True, False, True):
            posMax = posMin + posRange
        elif (haveMin, haveMax, haveRange) == (False, True, True):
            posMin = posMax - posRange
        elif (haveMin, haveMax, haveRange) == (False, False, True):
            # Assume range starts from zero.
            posMin = 0
            posMax = posRange
        else:
            raise Exception('No min, max or range specified for stage %s.' % self.name)

        result = []
        # Create handler without movement callbacks.
        handler = stagePositioner.PositionerHandler(
            "%d %s" % (axis, self.name), "%d stage motion" % axis, True,
            {'getMovementTime': lambda x, start, delta: (Decimal(0.05), Decimal(0.05))},
            axis, (posMin, posMax), (posMin, posMax))

        # Connect handler to analogue source to populate movement callbacks.
        handler.connectToAnalogSource(aHandler, aline, offset, gain)

        result.append(handler)
        return result
