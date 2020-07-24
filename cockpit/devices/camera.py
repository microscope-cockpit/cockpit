#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
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


## This module provides a dummy camera that generates test pattern images. 

from cockpit.devices import device

def Transform(tstr=None):
    """Desribes a simple transform: (flip LR, flip UD, rotate 90)"""
    if tstr:
        return tuple([bool(int(t)) for t in tstr.strip('()').split(',')])
    else:
        return (False, False, False)

## CameraDevice subclasses Device with some additions appropriate
# to any camera.
class CameraDevice(device.Device):
    def __init__(self, name, config):
        super().__init__(name, config)
        # baseTransform depends on camera orientation and is constant.
        self.baseTransform = Transform(config.get('transform', None))

    def updateTransform(self, pathTransform):
        """Apply a new pathTransform"""
        # pathTransform may change with changes in imaging path
        base = self.baseTransform
        # Flips cancel each other out. Rotations combine to flip both axes.
        lr = base[0] ^ pathTransform[0]
        ud = base[1] ^ pathTransform[1]
        rot = base[2] ^ pathTransform[2]
        if pathTransform[2] and base[2]:
            lr = not lr
            ud = not ud
        self._setTransform((lr, ud, rot))

    def _setTransform(self, transform):
        # Sublcasses should override this if transforms are done on the device.
        self._transform = transform

    def finalizeInitialization(self):
        # Set fixed filter if defined in config
        if self.handler.wavelength is None and self.handler.dye is None:
            dye = self.config.get('dye', None)
            wavelength = self.config.get('wavelength', None)
            self.handler.updateFilter(dye, wavelength)
