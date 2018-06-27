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


#Gather the drawing primitives in one place to draw scaled vertex,
#circle, square and arrows.

from util import ftgl
from gui import FONTPATH

## Font for drawing text
try:
    font = ftgl.TextureFont(FONTPATH)
    font.setFaceSize(18)
except Exception as e:
    print ("Failed to make font:",e)

CIRCLE_SEGMENTS = 32
PI = 3.141592645
## Line thickness for the arrow
ARROW_LINE_THICKNESS = 3.5
## Bluntness of the arrowhead (pi/2 == totally blunt)
ARROWHEAD_ANGLE = numpy.pi / 6.0

## Draw an arrow from the first point along the specified vector.
def drawArrow(self, baseLoc, vector, color, arrowSize, arrowHeadSize):
    # Normalize.
    delta = vector / numpy.sqrt(numpy.vdot(vector, vector)) * arrowSize
    # Calculate angle, for the head of the arrow
    angle = numpy.arctan2(delta[1], delta[0])

    pointLoc = baseLoc + delta
    headLoc1 = pointLoc - numpy.array([numpy.cos(angle + ARROWHEAD_ANGLE), numpy.sin(angle + ARROWHEAD_ANGLE)]) * arrowHeadSize
    headLoc2 = pointLoc - numpy.array([numpy.cos(angle - ARROWHEAD_ANGLE), numpy.sin(angle - ARROWHEAD_ANGLE)]) * arrowHeadSize

    # Draw
    glColor3f(color[0], color[1], color[2])
    glLineWidth(ARROW_LINE_THICKNESS)
    glBegin(GL_LINES)
    self.scaledVertex(baseLoc[0], baseLoc[1])
    self.scaledVertex(pointLoc[0], pointLoc[1])
    glEnd()
    # Prevent the end of the line from showing through the
    # arrowhead by moving the arrowhead further along.
    pointLoc += delta * .1
    glBegin(GL_POLYGON)
    self.scaledVertex(headLoc1[0], headLoc1[1])
    self.scaledVertex(headLoc2[0], headLoc2[1])
    self.scaledVertex(pointLoc[0], pointLoc[1])
    glEnd()


## Draw some text at the specified location
def drawTextAt(self, loc, text, size, color = (0, 0, 0)):
    loc = self.scaledVertex(loc[0], loc[1], True)
    aspect = float(self.height) / self.width
    glPushMatrix()
    glTranslatef(loc[0], loc[1], 0)
    glScalef(size * aspect, size, size)
    glColor3fv(color)
    gui.drawShapes.font.render(text)
    glPopMatrix()


## Draw a circle of radius r centred on x0, y0 with n vertices.
def drawScaledCircle(self, x0, y0, r, n, offset=True):
    dTheta = 2. * PI / n
    cosTheta = numpy.cos(dTheta)
    sinTheta = numpy.sin(dTheta)
    if offset:
        x0=x0-self.offset[0]
        y0 =y0+self.offset[1]
    x = r
    y = 0.

    glBegin(GL_LINE_LOOP)
    for i in range(n):
        glVertex2f(-(x0 + x), y0 + y)
        xOld = x
        x = cosTheta * x - sinTheta * y
        y = sinTheta * xOld + cosTheta * y
    glEnd()


## Draw a rectangle centred on x0, y0 of width w and height h.
def drawScaledRectangle(self, x0, y0, w, h, offset=True):
    dw = w / 2.
    dh = h / 2.
    if offset:
        x0 = x0-self.offset[0]
        y0 = y0+self.offset[1]
    ps = [(x0-dw, y0-dh),
          (x0+dw, y0-dh),
          (x0+dw, y0+dh),
          (x0-dw, y0+dh)]

    glBegin(GL_LINE_LOOP)
    for i in range(-1, 4):
        glVertex2f(-ps[i][0], ps[i][1])
    glEnd()
# Draw a crosshairs at the specified position with the specified color.
# By default make the size of the crosshairs be really big.
def drawCrosshairs(self, position, color, size = None):
    xSize = ySize = size
    if size is None:
        xSize = ySize = 100000
    x, y = position
    #if no offset defined we can't apply it!
    if hasattr(self, 'offset'):
        x = x-self.offset[0]
        y = y-self.offset[1]

    # Draw the crosshairs
    glColor3f(*color)
    glBegin(GL_LINES)
    glVertex2d(-x - xSize, y)
    glVertex2d(-x + xSize, y)
    glVertex2d(-x, y - ySize)
    glVertex2d(-x, y + ySize)
    glEnd()

    glBegin(GL_LINE_LOOP)
    # Draw the box.
    for i, j in [(-1, -1), (-1, 1), (1, 1), (1, -1)]:
        glVertex2d(-x + i * self.crosshairBoxSize / 2,
                y + j * self.crosshairBoxSize / 2)
    glEnd()
