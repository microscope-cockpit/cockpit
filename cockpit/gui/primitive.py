from OpenGL.GL import *
from ctypes import c_float
import numpy

CIRCLE_SEGMENTS = 32
PI = 3.141592654


class Primitive(object):
    @staticmethod
    def factory(spec, isOffset=True):
        # Spec is a type and some data
        if spec.type in ['c', 'C']:
            return Circle(*spec.data, CIRCLE_SEGMENTS,
                          isOffset)
        if spec.type in ['r', 'R']:
            return Rectangle(*spec.data, isOffset=isOffset)


    def __init__(self, *args):
        self._vbo = None
        self._numVertices = 0


    def makeVBO(self, vertices):
        if self._vbo is None:
            self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, len(vertices)*4,
                    (c_float*len(vertices))(*vertices), GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._numVertices = len(vertices) // 2


    def render(self, offset=None):
        if self.isOffset and offset is not None:
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glTranslatef(*offset, 0, 0)
        glEnableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glVertexPointer(2, GL_FLOAT, 0, None)
        glDrawArrays(GL_LINE_LOOP, 0, self._numVertices)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glDisableClientState(GL_VERTEX_ARRAY)
        if self.isOffset and offset is not None:
            glPopMatrix()


class Circle(Primitive):
    def __init__(self, x0, y0, r, n=CIRCLE_SEGMENTS, isOffset=True):
        Primitive.__init__(self)
        self.isOffset = isOffset
        dTheta = 2. * PI / n
        cosTheta = numpy.cos(dTheta)
        sinTheta = numpy.sin(dTheta)
        x = r
        y = 0.

        vs = []
        for i in range(n):
            vs.extend([-(x0 + x), y0 + y])
            xOld = x
            x = cosTheta * x - sinTheta * y
            y = sinTheta * xOld + cosTheta * y

        self.makeVBO(vs)


class Rectangle(Primitive):
    def __init__(self, x0, y0, w, h, isOffset=True):
        Primitive.__init__(self)
        self.isOffset = isOffset
        dw = w / 2.
        dh = h / 2.

        vs  = [-(x0 - dw), y0 - dh,
               -(x0 + dw), y0 - dh,
               -(x0 + dw), y0 + dh,
               -(x0 - dw), y0 + dh]

        self.makeVBO(vs)