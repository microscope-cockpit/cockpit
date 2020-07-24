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


## Given a wavelength in nm, return an RGB color tuple. 
def wavelengthToColor(wavelength, saturation=1):
    wavelength = float(wavelength)
    if wavelength == 0.0:
        return (192,192,192)
    # Convert wavelength to hue, with a color wheel that ranges from
    # blue (240 degrees) at 400nm to red (360 degrees) at 650nm by way of
    # green.
    hue = max(0, min(300, (650 - wavelength)))
    # Make value decrease as we leave the visible spectrum.
    decay = max(0, max(400 - wavelength, wavelength - 650))
    # Don't let value decay too much.
    value = max(.5, 1 - decay / 200.0)
    r, g, b = hsvToRgb(hue, saturation, value)
    return tuple(int(val * 255) for val in (r, g, b))


## Convert to RGB. Taken from Pyrel:
# https://bitbucket.org/derakon/pyrel/src/7c30ed65e11b5f483737df615fcc607ab6c47d8b/gui/colors.py?at=master
# In turn, adapted from http://www.cs.rit.edu/~ncs/color/t_convert.html
def hsvToRgb(hue, saturation, value):
    if saturation == 0:
        # Greyscale.
        return (value, value, value)

    hue = hue % 360
    hue /= 60.0
    sector = int(hue)
    hueDecimal = hue - sector # Portion of hue after decimal point
    p = value * (1 - saturation)
    q = value * (1 - saturation * hueDecimal)
    t = (1 - saturation * (1 - hueDecimal))

    if sector == 0:
        return (value, t, p)
    if sector == 1:
        return (q, value, p)
    if sector == 2:
        return (p, value, t)
    if sector == 3:
        return (p, q, value)
    if sector == 4:
        return (t, p, value)
    return (value, p, q)
