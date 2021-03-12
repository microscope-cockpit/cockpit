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

import typing

import numpy
from OpenGL.GL import *
import traceback
import wx

from cockpit import events
from cockpit.gui.primitive import Primitive
import cockpit.gui.dialogs.getNumberDialog
import cockpit.interfaces
import cockpit.interfaces.stageMover
import cockpit.util.logger

from cockpit.gui.macroStage import macroStageBase


class _StagePositionEntryDialog(wx.Dialog):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title="Move Stage")

        self._spins = []
        position = cockpit.interfaces.stageMover.getPosition()
        limits = cockpit.interfaces.stageMover.getSoftLimits()
        for i in range(3):
            self._spins.append(wx.SpinCtrlDouble(
                self,
                min=limits[i][0],
                max=limits[i][1],
                initial=position[i]
            ))

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(self, label="Select stage position"),
                  wx.SizerFlags().Border().Centre())

        spins_sizer = wx.FlexGridSizer(cols=2, gap=(0, 0))
        for spin, name in zip(self._spins, ['X', 'Y', 'Z']):
            spins_sizer.Add(wx.StaticText(self, label=name),
                            wx.SizerFlags().Border().Centre())
            spins_sizer.Add(spin, wx.SizerFlags().Border().Expand())
        sizer.Add(spins_sizer, wx.SizerFlags().Border().Centre())

        buttons_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(buttons_sizer, wx.SizerFlags().Border().Centre())

        self.SetSizerAndFit(sizer)

    def GetValue(self) -> typing.Tuple[float, float, float]:
        return [s.GetValue() for s in self._spins]


def GoToXYZDialog(parent: wx.Window) -> None:
    position_dialog = _StagePositionEntryDialog(parent)
    if position_dialog.ShowModal() != wx.ID_OK:
        return

    newPos = position_dialog.GetValue()
    # Work out if we will be ouside the limits of the current stage
    # This should be a method of the StageMover interface (see #616)
    position = cockpit.interfaces.stageMover.getPosition()
    posDelta = [
            newPos[0] - position[0],
            newPos[1] - position[1],
            newPos[2] - position[2],
        ]
    originalHandlerIndex = wx.GetApp().Stage.curHandlerIndex
    currentHandlerIndex = originalHandlerIndex
    allPositions = cockpit.interfaces.stageMover.getAllPositions()
    for axis in range(3):
        if posDelta[axis] ** 2 > 0.001:
            limits = cockpit.interfaces.stageMover.getIndividualHardLimits(axis)
            currentpos = allPositions[currentHandlerIndex][axis]
            if (
                # off bottom
                currentpos + posDelta[axis]
                < (limits[currentHandlerIndex][0])
            ) or (
                # off top
                currentpos + posDelta[axis]
                > (limits[currentHandlerIndex][1])
            ):
                currentHandlerIndex -= 1  # go to a bigger handler index
            if currentHandlerIndex < 0:
                return
    wx.GetApp().Stage.curHandlerIndex = currentHandlerIndex
    cockpit.interfaces.stageMover.goTo(newPos)
    wx.GetApp().Stage.curHandlerIndex = originalHandlerIndex


## This class shows a high-level view of where the stage is in XY space, and
# how it will move when controlled by the keypad. It includes displays
# of where saved sites are, where mosaic tiles are, the current
# XY coordinates, and so on.
class MacroStageXY(macroStageBase.MacroStageBase):
    ## Instantiate the object. Just calls the parent constructor and sets
    # up the mouse event.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ## Objective offset info to get correct position and limits
        self.offset = wx.GetApp().Objectives.GetOffset()
        ## Whether or not to draw the mosaic tiles
        self.shouldDrawMosaic = True
        ## True if we're in the processing of changing the soft motion limits.
        self.amSettingSafeties = False
        ## Position the mouse first clicked when setting safeties, or None if
        # we aren't setting safeties.
        self.firstSafetyMousePos = None
        ## Last seen mouse position
        self.lastMousePos = [0, 0]

        primitive_specs = wx.GetApp().Config['stage'].getlines('primitives', [])
        self._primitives = [Primitive.factory(spec) for spec in primitive_specs]

        hardLimits = cockpit.interfaces.stageMover.getHardLimits()
        self.minX, self.maxX = hardLimits[0]
        self.minY, self.maxY = hardLimits[1]
        ## X extent of the stage, in microns.
        stageWidth = self.maxX - self.minX
        ## Y extent of the stage, in microns.
        stageHeight = self.maxY - self.minY
        ## Max of X or Y stage extents.
        self.maxExtent = max(stageWidth, stageHeight)
        ## X and Y view extent.
        if stageHeight > stageWidth:
            self.viewExtent = 1.2 * stageHeight
            self.viewDeltaY = stageHeight * 0.1
        else:
            self.viewExtent = 1.05 * stageWidth
            self.viewDeltaY = stageHeight * 0.05
        # Push out the min and max values a bit to give us some room around
        # the stage to work with. In particular we need space below the display
        # to show our legend.
        self.centreX = ((self.maxX - self.minX) / 2) + self.minX
        self.centreY = ((self.maxY - self.minY) / 2) + self.minY
        self.minX = self.centreX - self.viewExtent / 2
        self.maxX = self.centreX + self.viewExtent / 2
        self.minY = self.centreY - self.viewExtent / 2 - self.viewDeltaY
        self.maxY = self.centreY + self.viewExtent / 2 - self.viewDeltaY

        ## Size of text to draw. I confess I don't really understand how this
        # corresponds to anything, but it seems to work out.
        self.textSize = .004

        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftClick)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDoubleClick)
        self.Bind(wx.EVT_RIGHT_UP, self.OnRightClick)
        self.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDoubleClick)
        # Bind context menu event to None to prevent main window context menu
        # being displayed in preference to our own.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)
        events.subscribe("soft safety limit", self.onSafetyChange)
        self.SetToolTip(wx.ToolTip("Left double-click to move the stage. " +
                "Right click for gotoXYZ and double-click to toggle displaying of mosaic " +
                "tiles."))

        wx.GetApp().Objectives.Bind(
            cockpit.interfaces.EVT_OBJECTIVE_CHANGED,
            self._OnObjectiveChanged,
        )

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
            width, height = self.GetClientSize()*self.GetContentScaleFactor()

            glViewport(0, 0, width, height)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            squareOffsets = [(0, 0), (0, 1), (1, 1), (1, 0)]
            stepSizes = cockpit.interfaces.stageMover.getCurStepSizes()[:2]

            # Draw hard stage motion limits
            hardLimits = cockpit.interfaces.stageMover.getHardLimits()[:2]
            # Rearrange limits to (x, y) tuples.
            hardLimits = list(zip(hardLimits[0], hardLimits[1]))
            stageHeight = abs(hardLimits[1][0] - hardLimits[1][1])

            # Set up transform from stage to screen units
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glOrtho(self.maxX, self.minX, self.minY, self.maxY, -1.0, 1.0)

            #Loop over objective offsets to draw limist in multiple colours.
            for obj in wx.GetApp().Objectives.GetHandlers():
                offset = obj.offset
                colour = obj.colour
                glLineWidth(4)
                if obj is not wx.GetApp().Objectives.GetCurrent():
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
                x1, x2 = safeties[0]
                y1, y2 = safeties[1]
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
                        (softLimits[0], (self.maxExtent * .1, 0)),
                        (softLimits[0], (0, self.maxExtent * .1)),
                        (softLimits[1], (-self.maxExtent * .1, 0)),
                        (softLimits[1], (0, -self.maxExtent * .1))]:
                    secondVertex = [vx + dx, vy + dy]
                    glVertex2f(vx-offset[0], vy+offset[1])
                    glVertex2f(secondVertex[0]-offset[0],
                                      secondVertex[1]+offset[1])
                glEnd()
                glLineWidth(1)
            # Now the coordinates. Only draw them if the soft limits aren't
            # the hard limits, to avoid clutter.
            if safeties != hardLimits:
                for i, (dx, dy) in enumerate([(4000, -700), (2000, 400)]):
                    x = softLimits[i][0]
                    y = softLimits[i][1]
                    self.drawTextAt((x + dx, y + dy),
                                    "(%d, %d)" % (x, y), size = self.textSize * .75)

            glDisable(GL_LINE_STIPPLE)

            # Draw device-specific primitives.
            # This uses vertex buffers with vertices in stage co-ordinates,
            # so need to update the modelview matrix to render them in the
            # right place.
            glEnable(GL_LINE_STIPPLE)
            glLineStipple(1, 0xAAAA)
            glColor3f(0.4, 0.4, 0.4)
            for primitive in self._primitives:
                primitive.render()
            glDisable(GL_LINE_STIPPLE)

            #Draw possibloe stage positions for current objective
            offset = wx.GetApp().Objectives.GetOffset()
            colour = wx.GetApp().Objectives.GetColour()
            glLineWidth(2)
            # Draw stage position
            motorPos = self.curStagePosition[:2]
            squareSize = self.maxExtent * .025
            glColor3f(*colour)
            glBegin(GL_LINE_LOOP)
            for (x, y) in squareOffsets:
                glVertex2f(motorPos[0]-offset[0] +
                                  squareSize * x - squareSize / 2,
                                  motorPos[1]+offset[1] +
                                  squareSize * y - squareSize / 2)
            glEnd()

            # Draw motion crosshairs
            glColor3f(1, 0, 0)
            glBegin(GL_LINES)
            for i, stepSize in enumerate(stepSizes):
                if stepSize is None:
                    # No step control along this axis.
                    continue
                offset = [0, 0]
                offset[i] = stepSize
                glVertex2f(motorPos[0] - offset[0], motorPos[1] - offset[1])
                glVertex2f(motorPos[0] + offset[0], motorPos[1] + offset[1])
            glEnd()

            # Draw direction of motion
            delta = motorPos - self.prevStagePosition[:2]

            if sum(numpy.fabs(delta)) > macroStageBase.MIN_DELTA_TO_DISPLAY:
                self.drawArrow((motorPos[0]- self.offset[0],
                                motorPos[1]+self.offset[1]), delta, (0, 0, 1),
                        arrowSize = self.maxExtent * .1,
                        arrowHeadSize = self.maxExtent * .025)
                glLineWidth(1)

            # The crosshairs don't always draw large enough to show,
            # so ensure that at least one pixel in the middle
            # gets drawn.
            glBegin(GL_POINTS)
            glVertex2f(motorPos[0]-self.offset[0],
                              motorPos[1]+self.offset[1])
            glEnd()

            # Draw scale bar
            glColor3f(0, 0, 0)
            glLineWidth(1)
            glBegin(GL_LINES)
            yOffset = self.minY + 0.9 * (self.viewDeltaY + 0.5 * (self.viewExtent - stageHeight))
            glVertex2f(hardLimits[0][0], yOffset)
            glVertex2f(hardLimits[0][1], yOffset)
            # Draw notches in the scale bar every 1mm.
            for scaleX in range(int(hardLimits[0][0]), int(hardLimits[0][1]) + 1000, 1000):
                width = self.viewExtent * .015
                if scaleX % 5000 == 0:
                    width = self.viewExtent * .025
                y1 = yOffset - width / 2
                y2 = yOffset + width / 2
                glVertex2f(scaleX, y1)
                glVertex2f(scaleX, y2)
            glEnd()
            glLineWidth(1)

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

    def OnRightClick(self, event) -> None:
        del event
        GoToXYZDialog(self.GetParent())

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
    def _OnObjectiveChanged(self, event: wx.CommandEvent) -> None:
        self.offset = wx.GetApp().Objectives.GetOffset()
        self.Refresh()
        event.Skip()
