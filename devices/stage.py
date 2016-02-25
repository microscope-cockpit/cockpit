
# coding: utf-8
""" stage.py: defines a base class for stage devices.

Copyright 2016 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import device
from config import config
from interfaces.stageMover import Primitive
import re
import wx

class StageDevice(device.Device):
    """StageDevice sublcasses Device with additions appropriate to any stage."""
        
    # CONFIG_NAME must be set as class variable when subclassed.
    CONFIG_NAME = None
    

    def __init__(self):
        """Initialise StageDevice."""
        super(StageDevice, self).__init__()
        # A list of primitives to draw on the macrostage display.
        self.primitives = None
    

    def getPrimitives(self):
        """Return a list of Primitives to draw on MacroStageXY display.

        On first call, we read a list of primitives from the config file.
        Primitives are defined as a config entry of the form:
            primitives:  c 1000 1000 100
                         r 1000 1000 100 100
        where:
            'c x0 y0 radius' defines a circle centred on x0, y0
            'r x0 y0 width height' defines a rectangle centred on x0, y0
        The primitive identifier may be in quotes, and values may be separated
        by any combination of spaces, commas and semicolons.
        """
        
        if self.CONFIG_NAME is None:
            # CONFIG_NAME was never set by the subclass.
            raise Exception('CONFIG_NAME not set when sublcassed.')


        if self.primitives is None:
            # Primitives not yet read from config.
            self.primitives = []
            if config.has_option(self.CONFIG_NAME, 'primitives'):
                primitives = config.get(self.CONFIG_NAME, 'primitives').split('\n')
                for pstr in primitives:
                    p = re.split('[ |,|;]*', re.sub("['|\"]", '', pstr))
                    pType = p[0]
                    pData = tuple(map(float, p[1:]))
                    self.primitives.append(Primitive(self, pType, pData))

        return self.primitives