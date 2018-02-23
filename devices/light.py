#!/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2018 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import Pyro4
from . import device
import depot
import handlers.lightSource
import util.colors


class SimpleLight(device.Device):
    """A simple light device.

    * may support external triggers
    * has no software interface to the hardware, so no power level control
    Sample config entry:
      [led source]
      type: LightDevice
      triggerSource: trigsource
      triggerLine: 1

      [trigsource]
      type: ExecutorDevice
      ...
    """
    def getHandlers(self):
        self.handlers = []
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        self.handlers.append(handlers.lightSource.LightHandler(
            self.name + ' toggle',
            self.name + ' light source',
            {'setEnabled': lambda name, on: None,
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime,
             'setExposing': lambda name, isOn: None,},
            self.config.get('wavelength', None),
            100,
            trighandler,
            trigline))

        return self.handlers