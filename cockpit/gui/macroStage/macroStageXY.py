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


import numpy
from OpenGL.GL import *
import traceback
import wx

from cockpit import events
from cockpit.gui.primitive import Primitive
import cockpit.gui.mosaic.window
import cockpit.interfaces.stageMover
import cockpit.util.logger

from . import macroStageBase

CIRCLE_SEGMENTS = 32

## This class shows a high-level view of where the stage is in XY space, and
# how it will move when controlled by the keypad. It includes displays
# of where saved sites are, where mosaic tiles are, the current
# XY coordinates, and so on.
class MacroStageXY(macroStageBase.MacroStageBase):
    ## Instantiate the object. Just calls the parent constructor and sets
    # up the mouse event.
    def __init__(self, *args, **kwargs):
        macroStageBase.MacroStageBase.__init__(self, *args, **kwargs)
        ## Whether or not to draw the mosaic tiles
        self.shouldDrawMosaic = True
        ## True if we're in the processing of changing the soft motion limits.
        self.amSettingSafeties = False
        ## Position the mouse first clicked when setting safeties, or None if
        # we aren't setting safeties.
        self.firstSafetyMousePos = None
        ## Last seen mouse position
        self.lastMousePos = [0, 0]
        ## Primitive objects - a map of specification to object.
        self.primitives = {}

        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftClick)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDoubleClick)
        self.Bind(wx.EVT_RIGHT_UP, self.OnRightClick)
        self.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDoubleClick)
        # Bind context menu event to None to prevent main window context menu
        # being displayed in preference to our own.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)
        events.subscribe("soft safety limit", self.onSafetyChange)
        events.subscribe('objective change', self.onObjectiveChange)
        self.SetToolTip(wx.ToolTip("Left double-click to move the stage. " +
                "Right click for gotoXYZ and double-click to toggle displaying of mosaic " +
                "tiles."))

    ## Dynamically calculate various parameters used for the drawing and modify
    ## the viewing area accordingly
    def calculateDrawingParams(self):
        # All measures are defined in the local (stage) space,
        # which has micrometers as units
        width, height = self.GetClientSize()
        hardLimits = cockpit.interfaces.stageMover.getHardLimits()
        combinedStageExtent = (hardLimits[0][1] - hardLimits[0][0]) + (hardLimits[1][1] - hardLimits[1][0])

        # Calculate the largest objective offsets
        _maxOffsetX = max([abs(offsets[0]) for offsets in self.listOffsets])
        _maxOffsetY = max([abs(offsets[1]) for offsets in self.listOffsets])

        # Initialise the view area to the area of the stage's hard limits, accounting for largest objective offsets
        self.minX, self.maxX = hardLimits[0]
        self.minY, self.maxY = hardLimits[1]
        self.minX -= _maxOffsetX
        self.maxX += _maxOffsetX
        self.minY -= _maxOffsetY
        self.maxY += _maxOffsetY

        # Calculate soft stage limit label metrics and ensure there is enough space to draw them
        softlimit_label_scale = 0.0018 * combinedStageExtent
        softlimit_label_line_height = ((self.font.getFontAscender() - self.font.getFontDescender()) *
                                            softlimit_label_scale)
        softlimit_label_offset = softlimit_label_line_height * 0.25
        self.maxY += softlimit_label_offset + softlimit_label_line_height
        self.minY -= softlimit_label_offset + softlimit_label_line_height

        # Calculate scale bar metrics and ensure there is enough space to draw it
        scalebar_height_major = softlimit_label_line_height
        scalebar_height_minor = softlimit_label_line_height * 0.5
        scalebar_position_v = self.minY - (scalebar_height_major / 2)  # vertical middle of scale bar
        self.minY = scalebar_position_v - (scalebar_height_major / 2)  # vertical bottom of scale bar

        # Ensure there is enough space to draw the coordinate and step size labels. The position is slightly offset,
        # proportionally to the line height, in order to create a small gap from the top soft stage limit label.
        coord_labels_scale_max = 0.0025 * combinedStageExtent
        coord_labels_line_height = ((self.font.getFontAscender() - self.font.getFontDescender()) *
                                          coord_labels_scale_max)
        coord_labels_position = (self.maxY + coord_labels_line_height * 0.25 +
                                      2 * coord_labels_line_height)
        self.maxY = coord_labels_position

        # Add margins for aesthetics and to ensure that all lines are entirely within the view area
        # NOTE: the margins may not be uniform
        minSideLength = min(self.maxX - self.minX, self.maxY - self.minY)
        margin = 0.05 * minSideLength
        self.minX -= margin
        self.maxX += margin
        self.minY -= margin
        self.maxY += margin

        # Correct the view area to preserve the aspect ratio of the stage
        aratio_viewport = width / height
        aratio_viewarea = (self.maxX - self.minX) / (self.maxY - self.minY)
        if aratio_viewport >= aratio_viewarea:
            # The viewport is wider than the stage => expose more horizontal scene space
            extra_space = ((aratio_viewport - aratio_viewarea) / aratio_viewarea) * (self.maxX - self.minX)
            self.minX -= extra_space / 2
            self.maxX += extra_space / 2
        else:
            # The viewport is taller than the stage => expose more vertical scene space
            extra_space = ((aratio_viewarea - aratio_viewport) / aratio_viewport) * (self.maxY - self.minY)
            self.minY -= extra_space / 2
            self.maxY += extra_space / 2

        return {
            "ssll": {
                "scale": softlimit_label_scale,
                "offset": softlimit_label_offset
            },
            "sb": {
                "tick_height_major": scalebar_height_major,
                "tick_height_minor": scalebar_height_minor,
                "position_v": scalebar_position_v
            },
            "cssl": {
                "scale_max": coord_labels_scale_max,
                "line_height": coord_labels_line_height,
                "position_v": coord_labels_position
            }
        }

    ## Safety limits have changed, which means we need to force a refresh.
    # \todo Redrawing everything just to tackle the safety limits is a bit
    # excessive.
    def onSafetyChange(self, axis, value, isMax):
        # We only care about the X and Y axes.
        if axis in [0, 1]:
            wx.CallAfter(self.Refresh)


    ## Draw the canvas. We draw the following:
    # - A blue dotted square representing the hard stage limits of
    #   [(4000, 4000), (25000, 25000)]
    # - A green dotted square representing the soft stage limits
    # - A red square centered on the current stage position
    # - A red crosshairs representing the stage motion delta
    # - When moving, a blue arrow indicating our direction of motion
    # - A purple dot for each saved site
    # - A black dot for each tile in the mosaic
    # - Device-defined primitives, e.g. to show individual sample locations.
    def onPaint(self, event = None):
        if not self.shouldDraw:
            return
        try:
            if not self.haveInitedGL:
                self.initGL()
                self.haveInitedGL = True

            dc = wx.PaintDC(self)
            self.SetCurrent(self.context)
            width, height = self.GetClientSize()

            glViewport(0, 0, width, height)

            dParams = self.calculateDrawingParams()

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            squareOffsets = [(0, 0), (0, 1), (1, 1), (1, 0)]
            stepSizes = cockpit.interfaces.stageMover.getCurStepSizes()[:2]

            # Draw hard stage motion limits
            hardLimits = cockpit.interfaces.stageMover.getHardLimits()[:2]
            # Rearrange limits to (x, y) tuples.
            hardLimits = list(zip(hardLimits[0], hardLimits[1]))
            maxStageExtent = max(hardLimits[1][0] - hardLimits[0][0], hardLimits[1][1] - hardLimits[0][1])

            # Set up transform from stage to screen units
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(self.maxX, self.minX, self.minY, self.maxY, -1.0, 1.0)

            #Loop over objective offsets to draw limist in multiple colours.
            safeties = []
            softLimits = []
            for obj in self.listObj:
                offset=self.objective.nameToOffset.get(obj)
                colour=self.objective.nameToColour.get(obj)
                glLineWidth(4)
                if obj is not self.objective.curObjective:
                    colour = (min(1,colour[0]+0.7),min(1,colour[1]+0.7),
                              min(1,colour[2]+0.7))
                    glLineWidth(2)
                glEnable(GL_LINE_STIPPLE)
                glLineStipple(3, 0xAAAA)
                glColor3f(*colour)
                glBegin(GL_LINE_LOOP)
                for (xIndex, yIndex) in squareOffsets:
                    glVertex2f(hardLimits[xIndex][0]-offset[0],
                               hardLimits[yIndex][1]+offset[1])
                glEnd()
                glDisable(GL_LINE_STIPPLE)

                # Draw soft stage motion limits -- a dotted box, solid black
                # corners, and coordinates. If we're currently setting safeties,
                # then the second corner is the current mouse position.
                safeties = cockpit.interfaces.stageMover.getSoftLimits()[:2]
                safeties = list(zip(safeties[0], safeties[1]))
                x1, y1 = safeties[0]
                x2, y2 = safeties[1]
                if self.firstSafetyMousePos is not None:
                    x1, y1 = self.firstSafetyMousePos
                    x2, y2 = self.lastMousePos
                    if x1 > x2:
                        x1, x2 = x2, x1
                    if y1 > y2:
                        y1, y2 = y2, y1
                softLimits = [(x1, y1), (x2, y2)]

                # First the dotted green box.
                glEnable(GL_LINE_STIPPLE)
                glLineWidth(2)
                glLineStipple(3, 0x5555)
                glColor3f(0, 1, 0)
                glBegin(GL_LINE_LOOP)
                for (x, y) in [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]:
                    glVertex2f(x-offset[0], y+offset[1])
                glEnd()
                glDisable(GL_LINE_STIPPLE)

                # Now the corners.
                glColor3f(0, 0, 0)
                glBegin(GL_LINES)
                for (vx, vy), (dx, dy) in [
                        (softLimits[0], (maxStageExtent * .1, 0)),
                        (softLimits[0], (0, maxStageExtent * .1)),
                        (softLimits[1], (-maxStageExtent * .1, 0)),
                        (softLimits[1], (0, -maxStageExtent * .1))]:
                    secondVertex = [vx + dx, vy + dy]
                    glVertex2f(vx-offset[0], vy+offset[1])
                    glVertex2f(secondVertex[0]-offset[0],
                                      secondVertex[1]+offset[1])
                glEnd()
                glLineWidth(1)
            # Now the coordinates. Only draw them if the soft limits aren't
            # the hard limits, to avoid clutter.
            if safeties != hardLimits:
                label_alignments = (
                    # Bottom right corner
                    {"alignment_h": "right", "alignment_v": "top"},
                    # Top left corner
                    {"alignment_h": "left", "alignment_v": "bottom"}
                )
                label_vertical_offsets = (
                    # Bottom right corner
                    -dParams["ssll"]["offset"],
                    # Top left corner,
                    dParams["ssll"]["offset"]
                )
                for i, (x, y) in enumerate(softLimits):
                    label = "({:.02f}, {:.02f})".format(x, y)
                    self.drawTextAt(
                        (x, y + label_vertical_offsets[i]),
                        label,
                        dParams["ssll"]["scale"],
                        dParams["ssll"]["scale"],
                        **label_alignments[i]
                    )

            glDisable(GL_LINE_STIPPLE)

            # Draw device-specific primitives.
            # This uses vertex buffers with vertices in stage co-ordinates,
            # so need to update the modelview matrix to render them in the
            # right place.
            glEnable(GL_LINE_STIPPLE)
            glLineStipple(1, 0xAAAA)
            glColor3f(0.4, 0.4, 0.4)
            primitives = cockpit.interfaces.stageMover.getPrimitives()
            for p in primitives:
                if p not in self.primitives:
                    self.primitives[p] = Primitive.factory(p)
                self.primitives[p].render()
            glDisable(GL_LINE_STIPPLE)

            #Draw possibloe stage positions for current objective
            obj = self.objective.curObjective
            offset=self.objective.nameToOffset.get(obj)
            colour=self.objective.nameToColour.get(obj)
            glLineWidth(2)
            # Draw stage position
            motorPos = self.curStagePosition[:2]
            squareSize = maxStageExtent * 0.025
            glColor3f(*colour)
            glBegin(GL_LINE_LOOP)
            for (x, y) in squareOffsets:
                glVertex2f(motorPos[0] - offset[0] + squareSize * x - squareSize / 2,
                           motorPos[1] + offset[1] + squareSize * y - squareSize / 2)
            glEnd()

            # Draw motion crosshairs
            glColor3f(1, 0, 0)
            glBegin(GL_LINES)
            for i, stepSize in enumerate(stepSizes):
                if stepSize is None:
                    # No step control along this axis.
                    continue
                hairLengths = [0, 0]
                hairLengths[i] = stepSize
                glVertex2f(motorPos[0] - offset[0] - hairLengths[0], motorPos[1] + offset[1] - hairLengths[1])
                glVertex2f(motorPos[0] - offset[0] + hairLengths[0], motorPos[1] + offset[1] + hairLengths[1])
            glEnd()

            # Draw direction of motion
            delta = motorPos - self.prevStagePosition[:2]

            if sum(numpy.fabs(delta)) > macroStageBase.MIN_DELTA_TO_DISPLAY:
                self.drawArrow((motorPos[0]- self.offset[0],
                                motorPos[1]+self.offset[1]), delta, (0, 0, 1),
                        arrowSize = maxStageExtent * .1,
                        arrowHeadSize = maxStageExtent * .025)
                glLineWidth(1)

            # Draw scale bar
            glColor3f(0, 0, 0)
            glLineWidth(1)
            glBegin(GL_LINES)
            glVertex2f(hardLimits[0][0], dParams["sb"]["position_v"])
            glVertex2f(hardLimits[1][0], dParams["sb"]["position_v"])
            # Draw notches in the scale bar every 1mm.
            for scaleX in range(int(hardLimits[0][0]), int(hardLimits[1][0]) + 1000, 1000):
                width = dParams["sb"]["tick_height_minor"]
                if scaleX % 5000 == 0:
                    width = dParams["sb"]["tick_height_major"]
                y1 = dParams["sb"]["position_v"] - width / 2
                y2 = dParams["sb"]["position_v"] + width / 2
                glVertex2f(scaleX, y1)
                glVertex2f(scaleX, y2)
            glEnd()
            glLineWidth(1)

            # Draw stage coordinates. Use a different color for the mover
            # currently under keypad control.
            allPositions = cockpit.interfaces.stageMover.getAllPositions()
            curControl = cockpit.interfaces.stageMover.getCurHandlerIndex()
            for index, axis_label in enumerate(["X:", "Y:"]):
                step = stepSizes[index]
                if step is None:
                    step = 0
                positions = [p[index] for p in allPositions]
                self.drawStagePosition(
                    axis_label,
                    (
                        hardLimits[0][0] + (hardLimits[1][0] - hardLimits[0][0]) / 2,
                        dParams["cssl"]["position_v"] - index * dParams["cssl"]["line_height"]
                    ),
                    positions,
                    curControl,
                    step,
                    dParams["cssl"]["scale_max"],
                    dParams["cssl"]["scale_max"],
                    alignment_h="centre"
                )

            events.publish('macro stage xy draw', self)

            glFlush()
            self.SwapBuffers()
            # Set the event, so our refreshWaiter() can update
            # our stage position info.
            self.drawEvent.set()
        except Exception as e:
            cockpit.util.logger.log.error("Exception drawing XY macro stage: %s", e)
            cockpit.util.logger.log.error(traceback.format_exc())
            self.shouldDraw = False


    ## Set one part of the stage motion limits.
    def setXYLimit(self, pos = None):
        if pos is None:
            # Use current stage position
            pos = self.curStagePosition
        if self.firstSafetyMousePos is None:
            # This is the first click for setting safeties.
            self.firstSafetyMousePos = [pos[0], pos[1]]
        else:
            # Set the second corner, then ensure that the "min" and "max"
            # values are in the right order.
            x1, y1 = self.firstSafetyMousePos
            x2, y2 = pos
            if x1 > x2:
                x1, x2 = x2, x1
            if y1 > y2:
                y1, y2 = y2, y1
            cockpit.interfaces.stageMover.setSoftMin(0, x1)
            cockpit.interfaces.stageMover.setSoftMax(0, x2)
            # Add 1 to prevent rounding issues relative to current position.
            cockpit.interfaces.stageMover.setSoftMin(1, y1 + 1)
            cockpit.interfaces.stageMover.setSoftMax(1, y2 + 1)
            self.amSettingSafeties = False
            self.firstSafetyMousePos = None
            self.Refresh()


    ## Moved the mouse. Record its position
    def OnMouseMotion(self, event):
        if self.amSettingSafeties and self.firstSafetyMousePos:
            # Need to redraw to show the new safeties.
            self.lastMousePos = self.remapClick(event.GetPosition())
            self.Refresh()


    ## Clicked the left mouse button. Set safeties if we're in that mode.
    def OnLeftClick(self, event):
        if self.amSettingSafeties:
            safeLoc = self.remapClick(event.GetPosition())
            self.setXYLimit(safeLoc)


    ## Double-clicked the left mouse button. Move to the clicked location.
    def OnLeftDoubleClick(self, event):
        originalMover= cockpit.interfaces.stageMover.mover.curHandlerIndex
        #Quick hack to get deepsim working need to check if we can do it
        #properly.  Should really check to see if we can move, and by that
        #distance with exisiting mover
        cockpit.interfaces.stageMover.mover.curHandlerIndex = 0

        cockpit.interfaces.stageMover.goToXY(self.remapClick(event.GetPosition()))

        #make sure we are back to the expected mover
        cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover

    def OnRightClick(self, event):
        position = cockpit.interfaces.stageMover.getPosition()
        values=cockpit.gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                self.GetParent(),
                "Go To XYZ",('X','Y','Z'),
                position,
                atMouse=True)
        newPos=[float(values[0]),float(values[1]),float(values[2])]
#Work out if we will be ouside the limits of the current stage
        posDelta = [newPos[0]-position[0],newPos[1]-position[1],newPos[2]-position[2]]
        originalHandlerIndex = cockpit.interfaces.stageMover.mover.curHandlerIndex
        currentHandlerIndex = originalHandlerIndex
        allPositions=cockpit.interfaces.stageMover.getAllPositions()
        for axis in range(3):
            if (posDelta[axis]**2 > .001 ):
                    limits = cockpit.interfaces.stageMover.getIndividualHardLimits(axis)
                    currentpos = allPositions[currentHandlerIndex][axis]
                    if ((currentpos + posDelta[axis]<(limits[currentHandlerIndex][0])) # off bottom
                        or (currentpos + posDelta[axis]>(limits[currentHandlerIndex][1]))): #off top
                        currentHandlerIndex -= 1 # go to a bigger handler index
                    if currentHandlerIndex<0:
                        return False
        cockpit.interfaces.stageMover.mover.curHandlerIndex = currentHandlerIndex
        cockpit.interfaces.stageMover.goTo(newPos)
        cockpit.interfaces.stageMover.mover.curHandlerIndex = originalHandlerIndex
        return True


    ## Right-clicked the mouse. Toggle drawing of the mosaic tiles
    def OnRightDoubleClick(self, event):
        self.shouldDrawMosaic = not self.shouldDrawMosaic


    ## Remap a click location from pixel coordinates to realspace coordinates
    def remapClick(self, clickLoc):
        width, height = self.GetClientSize()
        x = float(width - clickLoc[0]) / width * (self.maxX - self.minX) + self.minX
        y = float(height - clickLoc[1]) / height * (self.maxY - self.minY) + self.minY
        return [x+self.offset[0], y-self.offset[1]]


    ## Switch mode so that clicking sets the safeties
    def setSafeties(self, event = None):
        self.amSettingSafeties = True

    ## Refresh display on objective change
    def onObjectiveChange(self, name, pixelSize, transform, offset, **kwargs):
        self.offset = offset
        self.Refresh()


