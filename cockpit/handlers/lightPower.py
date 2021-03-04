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

import concurrent.futures as futures
import time

from cockpit import depot
from cockpit.handlers import deviceHandler
import cockpit.util.logger
import cockpit.util.userConfig
import cockpit.util.threads


## This handler is for light sources where the power of the light can be
# controlled through software.
class LightPowerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - setPower(value): Set power level.
    # - getPower(): Get current output power level.
    # \param curPower Initial output power.
    # \param isEnabled True iff the handler can be interacted with.

    ## We use a class method to monitor output power by querying hardware.
    # A list of instances. Light persist until exit, so don't need weakrefs.
    _instances = []
    @classmethod
    @cockpit.util.threads.callInNewThread
    def _updater(cls):
        ## Monitor output power and tell controls to update their display.
        # Querying power status can block while I/O is pending, so we use a
        # threadpool.
        # A map of lights to queries.
        queries = {}
        with futures.ThreadPoolExecutor() as executor:
            while True:
                time.sleep(0.1)
                for light in cls._instances:
                    getPower = light.callbacks['getPower']
                    if light not in queries.keys():
                        queries[light] = executor.submit(getPower)
                    elif queries[light].done():
                        light.lastPower = queries[light].result()
                        queries[light] = executor.submit(getPower)


    def __init__(self, name, groupName, callbacks, wavelength, curPower: float,
                 isEnabled=True) -> None:
        # Validation:
        required = set(['getPower', 'setPower'])
        missing = required.difference(callbacks)
        if missing:
            e = Exception('%s %s missing callbacks: %s.' %
                            (self.__class__.__name__,
                             name,
                             ' '.join(missing)))
            raise e

        super().__init__(name, groupName, False, callbacks, depot.LIGHT_POWER)
        LightPowerHandler._instances.append(self)
        self.wavelength = wavelength
        self.lastPower = curPower
        self.powerSetPoint = None
        self.isEnabled = isEnabled


    def finalizeInitialization(self):
        super().finalizeInitialization()
        self._applyUserConfig()


    def _applyUserConfig(self):
        targetPower = cockpit.util.userConfig.getValue(self.name + '-lightPower', default = 0.01)
        try:
            self.setPower(targetPower)
        except Exception as e:
            cockpit.util.logger.log.warning("Failed to set prior power level %s for %s: %s" % (targetPower, self.name, e))


    def onSaveSettings(self):
        return self.powerSetPoint

    def onLoadSettings(self, settings):
        try:
            self.setPower(settings)
        except Exception as e:
            # Invalid power; just ignore it.
            print("Invalid power for %s: %s" % (self.name, settings))


    ## Toggle accessibility of the handler.
    def setEnabled(self, isEnabled):
        self.isEnabled = isEnabled


    ## Return True iff we're currently enabled (i.e. GUI is active).
    def getIsEnabled(self):
        return self.isEnabled


    ## Fetch the current laser power.
    def getPower(self):
        return self.callbacks['getPower']()

    ## Handle the user selecting a new power level.
    def setPower(self, power):
        if power < 0.0 or power > 1.0:
            raise RuntimeError("Tried to set invalid power %f for light %s"
                               % (power, self.name))
        self.callbacks['setPower'](power)
        self.powerSetPoint = power
        cockpit.util.userConfig.setValue(self.name + '-lightPower', power)


    ## Simple getter.
    def getWavelength(self):
        return self.wavelength


    ## Experiments should include the laser power.
    def getSavefileInfo(self):
        return "%s: %.1f" % (self.name, self.lastPower)

# Fire up the status updater.
LightPowerHandler._updater()
