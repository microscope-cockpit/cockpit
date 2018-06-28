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


from . import device
import cockpit.handlers.lightSource

CLASS_NAME = 'DummyLightsDevice'



class DummyLights(device.Device):
    def __init__(self, name="dummy lights", config={}):
        device.Device.__init__(self, name, config)
        ## Maps lightsource names to their exposure times.
        self.nameToExposureTime = dict()
        # Set priority to Inf to indicate that this is a dummy device.
        self.priority = float('inf')        
        self.deviceType = 'light source'


    def getHandlers(self):
        result = []
        for label, wavelength in [('405 shutter', 405),
                ('488 shutter', 488), 
                ('640 shutter', 640)]:
            # Set up lightsource handlers. Default to 100ms exposure time.
            handler = cockpit.handlers.lightSource.LightHandler(
                label, "%s light source" % label, 
                {'setEnabled': lambda *args: None,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime}, wavelength, 100)
            self.nameToExposureTime[handler.name] = 100
            result.append(handler)
        return result


    ## Change the exposure time for a light source.
    def setExposureTime(self, name, time):
        self.nameToExposureTime[name] = time


    ## Get the exposure time for a light source.
    def getExposureTime(self, name):
        return self.nameToExposureTime[name]

