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


from cockpit.util import ftgl
import numpy
import os
from OpenGL.GL import *
import threading
import time
import wx

from cockpit import events
import cockpit.gui
import cockpit.interfaces.stageMover
import cockpit.util.logger
from cockpit import depot


PI = 3.1415926

## @package cockpit.gui.macroStage
# This module contains the MacroStageBase base class, used by the MacroStageXY
# and MacroStageZ classes, as well as some shared constants.


## Number of times to update the view, per second.
UPDATE_FPS = 10
## Number of previous stage positions to keep in our history
HISTORY_SIZE = 5
## Don't bother showing a movement arrow for
# movements smaller than this.
MIN_DELTA_TO_DISPLAY = .01
## Line thickness for the arrow
ARROW_LINE_THICKNESS = 3.5
## Bluntness of the arrowhead (pi/2 == totally blunt)
ARROWHEAD_ANGLE = numpy.pi / 6.0


## This class handles some common code for the MacroStageXY and MacroStageZ
# classes.
class MacroStageBase(wx.glcanvas.GLCanvas):
    ## Create the MacroStage. Mostly, attach a timer to the main window so
    # that we can use it to trigger updates.
    def __init__(self, parent, size, id = -1, *args, **kwargs):
        wx.glcanvas.GLCanvas.__init__(self, parent, id, size = size, *args, **kwargs)

        ## WX context for drawing.
        self.context = wx.glcanvas.GLContext(self)
        ## Whether or not we have done some one-time-only logic.
        self.haveInitedGL = False
        ## Whether or not we should try to draw
        self.shouldDraw = True
        ## Font for drawing text
        try:
            self.font = ftgl.TextureFont(cockpit.gui.FONT_PATH)
            self.font.setFaceSize(18)
        except Exception as e:
            print ("Failed to make font:",e)

        ## X values below this are off the canvas. We leave it up to children
        # to fill in proper values for these.
        self.minX = 0
        ## X values above this are off the canvas
        self.maxX = 1000
        ## Y values below this are off the canvas
        self.minY = 0
        ## Y values above this are off the canvas
        self.maxY = 1000

        ## (X, Y, Z) vector describing the stage position as of the last
        # time we drew ourselves. We need this to display motion deltas.
        self.prevStagePosition = numpy.zeros(3)
        ## As above, but for the current position.
        self.curStagePosition = numpy.zeros(3)
        ## Event used to indicate when drawing is done, so we can update
        # the above.
        self.drawEvent = threading.Event()

        ## (dX, dY, dZ) vector describing the stage step sizes as of the last
        # time we drew ourselves.
        self.prevStepSizes = numpy.zeros(3)
        ## As above, but represents our knowledge of the current sizes.
        self.curStepSizes = numpy.zeros(3)
        
        ##objective offset info to get correct position and limits
        self.objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.listObj = list(self.objective.nameToOffset.keys())
        self.listOffsets = list(self.objective.nameToOffset.values())
        self.offset = self.objective.getOffset()
 
        ## Boolean to just force a redraw.
        self.shouldForceRedraw = False

        ## Thread that ensures we don't spam redisplaying ourselves.
        self.redrawTimerThread = threading.Thread(target=self.refreshWaiter, name="macrostage-refresh")
        self.redrawTimerThread.start()

        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_SIZE, lambda event: event)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: event) # Do nothing, to avoid flashing
        events.subscribe(events.STAGE_POSITION, self.onMotion)
        events.subscribe("stage step size", self.onStepSizeChange)
        events.subscribe("stage step index", self.onStepIndexChange)


    ## Set up some set-once things for OpenGL.
    def initGL(self):
        self.SetCurrent(self.context)
        glClearColor(1.0, 1.0, 1.0, 0.0)


    ## Update our marker of where the stage currently is. This will indirectly
    # cause us to redisplay ourselves in a bit, thanks to self.refreshWaiter.
    def onMotion(self, axis, position):
        self.curStagePosition[axis] = position


    ## Step sizes have changed, which means we get to redraw.
    # \todo Redrawing *everything* at this stage seems a trifle excessive.
    def onStepSizeChange(self, axis, newSize):
        self.curStepSizes[axis] = newSize


    ## Step index has changed, so the highlighting on our step displays
    # is different.
    # \todo Same caveat as onStepSizeChange -- redrawing everything is 
    # excessive.
    def onStepIndexChange(self, index):
        self.shouldForceRedraw = True


    ## Wait until a minimum amount of time has passed since our last redraw
    # before we redraw again. Since we redraw when the stage moves or the
    # step size changes, and these events may happen rapidly, this
    # prevents us from spamming OpenGL calls.
    def refreshWaiter(self):
        while True:
            if not self:
                # Our window has been deleted; we're done here.
                return
            if (numpy.any(self.curStagePosition != self.prevStagePosition) or
                    numpy.any(self.curStepSizes != self.prevStepSizes) or
                    self.shouldForceRedraw):
                self.drawEvent.clear()
                wx.CallAfter(self.Refresh)
                self.drawEvent.wait()
                self.prevStagePosition[:] = self.curStagePosition
                self.prevStepSizes[:] = self.curStepSizes
                # Draw again after a delay, so that motion arrows get
                # cleared.
                time.sleep(.25)
                self.drawEvent.clear()
                wx.CallAfter(self.Refresh)
                self.drawEvent.wait()
                self.shouldForceRedraw = False
            time.sleep(.1)


    ## Rescale the input value to be in the range 
    # (self.min[X|Y], self.max[X|Y]), flip the X axis, and call glVertex2f on
    # the result. Or return the value instead if shouldReturn is true. The 
    # basic idea here is to go from stage coordinates to view coordinates.
    def scaledVertex(self, x, y, shouldReturn = False):
        newX = -1 * ((x - self.minX) / float(self.maxX - self.minX) * 2 - 1)
        newY = (y - self.minY) / float(self.maxY - self.minY) * 2 - 1
        if shouldReturn:
            return (newX, newY)
        else:
            glVertex2f(newX, newY)

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
        glVertex2f(baseLoc[0], baseLoc[1])
        glVertex2f(pointLoc[0], pointLoc[1])
        glEnd()
        # Prevent the end of the line from showing through the
        # arrowhead by moving the arrowhead further along.
        pointLoc += delta * .1
        glBegin(GL_POLYGON)
        glVertex2f(headLoc1[0], headLoc1[1])
        glVertex2f(headLoc2[0], headLoc2[1])
        glVertex2f(pointLoc[0], pointLoc[1])
        glEnd()

    def drawTextAt(self, loc, text, scale_x=1.0, scale_y=1.0, alignment_h="left", alignment_v="bottom",
                    colour=(0.0, 0.0, 0.0, 1.0), scale_axis_x=-1.0, scale_axis_y=1.0, draw_bbox=False):
        """Draw a line of text.

        Draw a line of text at the given location. Optionally, draw the bounding box as well.
        Possible alignment arguments are:
            horizontal: left, baseline, centre, right
            vertical: top, middle, baseline, bottom
        The format of the colour argument is RGBA, range from 0 to 1.0.

        Args:
            loc (tuple of int): The location, in OpenGL units, at which to draw the text.
            text (str): The text to be drawn.
            scale_x (float): The scaling factor applied in the horizontal direction.
            scale_y (float): The scaling factor applied in the vertical direction.
            alignment_h (str): The horizontal alignment of the text with respect to the location.
            alignment_v (str): The vertical alignment of the text with respect to the location.
            colour (tuple of floats): The colour used for both the text and the bounding box.
            scale_axis_x (float): The scaling factor of the x axis. Expect only -1.0 or 1.0.
            scale_axis_y (float): The scaling factor of the y axis. Expect only -1.0 or 1.0.
            draw_bbox (boolean): Whether to draw the bounding box of the text.

        """
        # Save context
        prev_mmode = glGetInteger(GL_MATRIX_MODE)
        # Obtain a bounding box of the given string
        bbox = self.font.getFontBBox(text)
        # Calculate alignment offsets
        alignment_h_offset = (0 - bbox[0]) * scale_axis_x
        alignment_v_offset = (0 - bbox[1]) * scale_axis_y
        if alignment_h == "centre":
            # Subtract half of the bbox width
            alignment_h_offset -= ((bbox[3] - bbox[0]) / 2) * scale_axis_x
        elif alignment_h == "right":
            # Subtract the entire bbox width
            alignment_h_offset -= (bbox[3] - bbox[0]) * scale_axis_x
        elif alignment_h == "baseline":
            # The baseline point is (0, 0)
            alignment_h_offset = 0
        if alignment_v == "middle":
            # Subtract half of the bbox height
            alignment_v_offset -= ((bbox[4] - bbox[1]) / 2) * scale_axis_y
        elif alignment_v == "top":
            # Subtract the entire bbox height
            alignment_v_offset -= (bbox[4] - bbox[1]) * scale_axis_y
        elif alignment_v == "baseline":
            # The baseline point is (0, 0)
            alignment_v_offset = 0
        # Coordinate transformation
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glTranslatef(loc[0] + alignment_h_offset * scale_x, loc[1] + alignment_v_offset * scale_y, 0.0)
        glScalef(scale_x * scale_axis_x, scale_y * scale_axis_y, 1.0)
        # Render the text
        glColor4f(*colour)
        self.font.render(text)
        # Draw the bounding box
        if draw_bbox:
            glBegin(GL_LINE_LOOP)
            glVertex2f(bbox[0], bbox[1])
            glVertex2f(bbox[3], bbox[1])
            glVertex2f(bbox[3], bbox[4])
            glVertex2f(bbox[0], bbox[4])
            glEnd()
        # Restore context
        glPopMatrix()
        glMatrixMode(prev_mmode)

    def drawStagePosition(self, label, drawLoc, positions, highlightIndex, stepSize, scale_max_x, scale_max_y,
                           scale_axis_x=-1.0, scale_axis_y=1.0, alignment_h="left", alignment_v="top",
                           hl_colour=(0.0, 0.5, 0.0, 1.0)):
        """Draw a stage position line of text.

        Draw a specially formatted line of text, describing the position of an entity such as an axis, as well as its
        step size. If there is more than one not-None position, then are all drawn next to each other. The position
        with index highlightIndex is coloured differently. The scaling factors are applied directly to the label,
        whereas the rest of the text uses 0.75 of the same factors. Possible alignment arguments are:
            horizontal: left, baseline, centre, right
            vertical: top, middle, baseline, bottom
        The format of the colour argument is RGBA, range from 0 to 1.0.

        Args:
            label (str): The label of the entity, whose position and step size are being drawn.
            drawLoc (tuple of int): The location, in OpenGL units, at which to draw the line of text.
            positions (list of float): The entity positions. All None values are skipped.
            highlightIndex (int): The index of the position to highlight.
            stepSize (float): The size of the entity's step.
            scale_max_x (float): The scaling factor applied to the label in the horizontal direction.
            scale_max_y (float): The scaling factor applied to the label in the vertical direction.
            scale_axis_x (float): The scaling factor of the x axis. Expect only -1.0 or 1.0.
            scale_axis_y (float): The scaling factor of the y axis. Expect only -1.0 or 1.0.
            alignment_h (str): The horizontal alignment of the text with respect to the location.
            alignment_v (str): The vertical alignment of the text with respect to the location.
            hl_colour (tuple of floats): The colour used for highlighting one of the positions.

        """
        text_pos = list(drawLoc)
        # Calculate the width of a space character
        space_char_bbox = self.font.getFontBBox("  ")  # it's actually returning the bbox of a single space
        space_char_width = (space_char_bbox[3] - space_char_bbox[0]) * scale_max_x
        # Pre-calculate the total width of all the text that will be drawn
        total_text_width = 0.0
        bbox_axis = self.font.getFontBBox(label)
        total_text_width += ((bbox_axis[3] - bbox_axis[0]) * scale_max_x + space_char_width) * scale_axis_x
        bbox_miny = bbox_axis[1] * scale_max_y * scale_axis_y
        bbox_maxy = bbox_axis[4] * scale_max_y * scale_axis_y
        for pos in positions:
            if pos is None:
                continue
            bbox_coord = self.font.getFontBBox("{:5.2f}".format(pos))
            total_text_width += ((bbox_coord[3] - bbox_coord[0]) * scale_max_x * 0.75 + space_char_width) * scale_axis_x
            bbox_miny = min(bbox_miny, bbox_coord[1] * scale_max_y * 0.75 * scale_axis_y)
            bbox_maxy = max(bbox_maxy, bbox_coord[4] * scale_max_y * 0.75 * scale_axis_y)
        total_text_width += (space_char_width * 3) * scale_axis_x
        bbox_step = self.font.getFontBBox("step: {:4.2f}um".format(stepSize))
        total_text_width += ((bbox_step[3] - bbox_step[0]) * scale_max_x * 0.75) * scale_axis_x
        bbox_miny = min(bbox_miny, bbox_step[1] * scale_max_y * 0.75 * scale_axis_y)
        bbox_maxy = max(bbox_maxy, bbox_step[4] * scale_max_y * 0.75 * scale_axis_y)
        # Calculate alignment offsets and apply them to the initial text position
        alignment_offset_h = (0 - bbox_axis[0]) * scale_axis_x
        if alignment_h == "centre":
            alignment_offset_h = total_text_width / 2
        elif alignment_h == "right":
            alignment_offset_h = total_text_width
        elif alignment_h == "baseline":
            alignment_offset_h = 0
        text_pos[0] -= alignment_offset_h
        alignment_offset_v = bbox_maxy
        if alignment_v == "baseline":
            alignment_offset_v = 0
        elif alignment_v == "middle":
            alignment_offset_v = (bbox_maxy - bbox_miny) / 2
        elif alignment_v == "bottom":
            alignment_offset_v = bbox_miny
        text_pos[1] -= alignment_offset_v
        # Draw the axis label and advance the text position horizontal location
        self.drawTextAt(text_pos, label, scale_max_x, scale_max_y, alignment_v="baseline", scale_axis_x=scale_axis_x)
        text_pos[0] += ((bbox_axis[3] - bbox_axis[0]) * scale_max_x + space_char_width) * scale_axis_x
        for i, pos in enumerate(positions):
            if pos is None:
                # No positioning for this axis.
                continue
            colour_args = {}
            if i == highlightIndex:
                colour_args["colour"] = hl_colour
            bbox_coord = self.font.getFontBBox("{:5.2f}".format(pos))
            self.drawTextAt(
                text_pos,
                "{:5.2f}".format(pos),
                scale_max_x * 0.75,
                scale_max_y * 0.75,
                alignment_v="baseline",
                scale_axis_x=scale_axis_x,
                **colour_args
            )
            text_pos[0] += ((bbox_coord[3] - bbox_coord[0]) * scale_max_x * 0.75 + space_char_width) * scale_axis_x
        # Add more horizontal spacings before the step size text
        text_pos[0] += (space_char_width * 3) * scale_axis_x
        # Draw the step size
        self.drawTextAt(
            text_pos,
            "step: {:4.2f}um".format(stepSize),
            scale_max_x * 0.75,
            scale_max_y * 0.75,
            alignment_v="baseline",
            scale_axis_x=scale_axis_x
        )

