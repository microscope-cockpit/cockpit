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


## This dummy device presents a selection of objectives to the user. In
# practice, the only difference you might have to make to this device to use
# it would be to change the available objectives and their pixel sizes.

from . import device
import handlers.objective
import re
PIXEL_PAT =  r"(?P<pixel_size>\d*[.]?\d*)"
LENSID_PAT = r"(?P<lensID>\d*)"
TRANSFORM_PAT = r"(?P<transform>\(\s*\d*\s*,\s*\d*\s*,\s*\d*\s*\))"
OFFSET_PAT = r"(?P<offset>\(\s*[-]?\d*\s*,\s*[-]?\d*\s*,\s*[-]?\d*\s*\))?"
COLOUR_PAT = r"(?P<colour>\(\s*[-]?\d*\s*,\s*[-]?\d*\s*,\s*[-]?\d*\s*\))?"

CONFIG_PAT = PIXEL_PAT + r"(\s*(,|;)\s*)?" + LENSID_PAT + r"(\s*(,|;)\s*)?" + TRANSFORM_PAT + r"(\s*(,|;)\s*)?" + OFFSET_PAT+ r"(\s*(,|;)\s*)?" + COLOUR_PAT

## Maps objective names to the pixel sizes for those objectives. This is the 
# amount of sample viewed by the pixel, not the physical size of the 
# pixel sensor.
DUMMY_OBJECTIVE_PIXEL_SIZES = {
        "40x": .2,
        "60xWater": .1,
        "60xOil": .1,
        "100xOil": .08,
        "150xTIRF": .06,
}


CLASS_NAME = 'ObjectiveDevice'

class ObjectiveDevice(device.Device):
    def __init__(self, name='objectives', config={}):
        device.Device.__init__(self, name, config)
        # Set priority to Inf to indicate that this is a dummy device.

    def getHandlers(self):
        pixel_sizes = {}
        transforms = {}
        offsets = {}
        lensIDs = {}
        colours = {}
        if not self.config:
            # No objectives section in config
            pixel_sizes = DUMMY_OBJECTIVE_PIXEL_SIZES
            transforms = {obj: (0,0,0) for obj in pixel_sizes.keys()}
            offsets = {obj: (0,0,0) for obj in pixel_sizes.keys()}
            lensIDs = {obj: 0 for obj in pixel_sizes.keys()}
            colours = {obj: (1,1,1) for obj in pixel_sizes.keys()}
        else:
            for obj, cfg in self.config.items():
                parsed = re.search(CONFIG_PAT, cfg)
                if not parsed:
                    # Could not parse config entry.
                    raise Exception('Bad config: objectives.')
                    # No transform tuple
                else:    
                    pstr = parsed.groupdict()['pixel_size']
                    lstr = parsed.groupdict()['lensID']
                    tstr = parsed.groupdict()['transform']
                    ostr =  parsed.groupdict()['offset']
                    cstr =  parsed.groupdict()['colour']
                    pixel_size = float(pstr)
                    lensID = int(lstr) if lstr else 0
                    transform = eval(tstr) if tstr else (0,0,0)
                    offset = eval(ostr) if ostr else (0,0,0)
                    colour = eval(cstr) if cstr else (1,0,0)
                pixel_sizes.update({obj: pixel_size})
                lensIDs.update({obj: lensID})
                transforms.update({obj: transform})
                offsets.update({obj: offset})
                colours.update({obj: colour})

        default = list(pixel_sizes.keys())[0]

        return [handlers.objective.ObjectiveHandler("objective",
                                                    "miscellaneous",
                                                    pixel_sizes,
                                                    transforms,
                                                    offsets,
                                                    colours,
                                                    lensIDs,
                                                    default)]
