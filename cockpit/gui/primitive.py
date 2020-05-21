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

from OpenGL.GL import *
from ctypes import c_float
import re
import numpy

CIRCLE_SEGMENTS = 32
PI = 3.141592654

class Primitive:
    """ A class for rendering primitives from devices.

    Stages can use primitives to show reference positions, such
    as well or sample grid locations. This class puts much of the
    code for this in one place.

    Note that canvases in separate contexts will each need their
    own Primitives - Primitives can not be shared between GL contexts.
    """
    @staticmethod
    def factory(spec):
        """
        Returns an appropriate primitive given a specification.
        Primitives are specified by a lines in a config entry of the form:
        primitives:  c 1000 1000 100
                     r 1000 1000 100 100
        where:
        'c x0 y0 radius' defines a circle centred on x0, y0
        'r x0 y0 width height' defines a rectangle centred on x0, y0
        The primitive identifier may be in quotes, and values may be separated
        by any combination of spaces, commas and semicolons.
        """
        p = re.split('[ |,|;]+', re.sub("['|\"]", '', spec))
        pType = p[0]
        pData = tuple(map(float, p[1:]))
        # Spec is a type and some data
        if pType in ['c', 'C']:
            return Circle(*pData, n=CIRCLE_SEGMENTS)
        if pType in ['r', 'R']:
            return Rectangle(*pData)


    def __init__(self, *args, **kwargs):
        self._vbo = None
        self._vertices = []
        self._numVertices = 0


    def makeVBO(self):
        vertices = self._vertices
        if self._vbo is None:
            self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, len(vertices)*4,
                    (c_float*len(vertices))(*vertices), GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._numVertices = len(vertices) // 2


    def render(self):
        if self._vbo is None:
            self.makeVBO()
        glEnableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glVertexPointer(2, GL_FLOAT, 0, None)
        glDrawArrays(GL_LINE_LOOP, 0, self._numVertices)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glDisableClientState(GL_VERTEX_ARRAY)


class Circle(Primitive):
    def __init__(self, x0, y0, r, n=CIRCLE_SEGMENTS):
        super().__init__()
        dTheta = 2. * PI / n
        cosTheta = numpy.cos(dTheta)
        sinTheta = numpy.sin(dTheta)
        x = r
        y = 0.

        vs = []
        for i in range(n):
            vs.extend([(x0 + x), y0 + y])
            xOld = x
            x = cosTheta * x - sinTheta * y
            y = sinTheta * xOld + cosTheta * y
        self._vertices = vs


class Rectangle(Primitive):
    def __init__(self, x0, y0, w, h):
        super().__init__()
        dw = w / 2.
        dh = h / 2.

        vs  = [(x0 - dw), y0 - dh,
               (x0 + dw), y0 - dh,
               (x0 + dw), y0 + dh,
               (x0 - dw), y0 + dh]

        self._vertices = vs
