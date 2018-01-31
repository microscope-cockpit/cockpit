
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

from decimal import Decimal
from . import device
from interfaces.stageMover import Primitive, AXIS_MAP
from handlers import stagePositioner
import depot
import re

class StageDevice(device.Device):
    """StageDevice sublcasses Device with additions appropriate to any stage."""
    def __init__(self, name, config):
        """Initialise StageDevice."""
        super(StageDevice, self).__init__(name, config)
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
        if self.primitives is None:
            # Primitives not yet read from config.
            self.primitives = []
            if config.get('primitives'):
                primitives = config.get('primitives').split('\n')
                for pstr in primitives:
                    p = re.split('[ |,|;]*', re.sub("['|\"]", '', pstr))
                    pType = p[0]
                    pData = tuple(map(float, p[1:]))
                    self.primitives.append(Primitive(self, pType, pData))

        return self.primitives


class SimplePiezo(StageDevice):
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

    def setSafety(self, *args, **kwargs):
        pass

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

        # TODO - consider moving stepSizes creation to the handler.
        stepSizes = [self.config.get('minstep', (posMax - posMin) * 1e-5)]
        m = 5
        while True:
            next = m * stepSizes[-1]
            if next > (posMax - posMin) / 10.:
                break
            stepSizes.append(next)
            m = [2, 5][m == 2]

        result = []
        # Create handler without movement callbacks.
        handler = stagePositioner.PositionerHandler(
            "%d %s" % (axis, self.name), "%d stage motion" % axis, True,
            {'getMovementTime': lambda x, start, delta: (Decimal(0.05), Decimal(0.05)) ,
             'cleanupAfterExperiment': None,
             'setSafety': self.setSafety},
            axis, stepSizes, min(4, len(stepSizes)),
            (posMin, posMax), (posMin, posMax))

        # Connect handler to analogue source to populate movement callbacks.
        handler.connectToAnalogSource(aHandler, aline, offset, gain)

        result.append(handler)
        return result