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
from . import deviceHandler

## This handler is a mix-in for handlers that abstract an analogue line.
class AnalogueHandlerMixin(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - getLineHandler(): return the analogue line handler.
    
    def __init__(self, name, groupName, isEligibleForExperiments, callbacks):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                isEligibleForExperiments, callbacks, 
                depot.GENERIC_DEVICE)


    ## Retrieve the real analogue line handler.
    def getLineHandler(self):
        return self.callbacks['getLineHandler']()
