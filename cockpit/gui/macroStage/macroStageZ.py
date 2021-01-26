#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
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

from OpenGL.GL import *
import traceback
import wx

from cockpit import events
import cockpit.interfaces.stageMover
import cockpit.util.logger
import cockpit.util.userConfig

from cockpit.gui.macroStage import macroStageBase


## Width of an altitude line.
HEIGHT_LINE_WIDTH = 3

## Distance in microns to include beneath the Z safety min in the histogram
HISTOGRAM_MIN_PADDING = 25
## Thickness of each line in the histogram
HISTOGRAM_LINE_WIDTH = 3
## Size of buckets in microns to use when generating altitude histogram
ALTITUDE_BUCKET_SIZE = 3

## Amount, in microns, of padding to add on either end of the mini-histogram
MINI_HISTOGRAM_PADDING = 1

#Size of secondar histogram if no fine motion stage in microns
SECONDARY_HISTOGRAM_SIZE = 50

## This is a simple container class for histogram display info.
# \todo Refactor histogram drawing logic into this class.
class Histogram():
    def __init__(self, minAltitude, maxAltitude,
                 xOffset, minY, maxY, width, shouldLabel, margin, data = None):
        ## Altitude in microns below which we do not display
        self.minAltitude = minAltitude
        ## Altitude in microns above which we do not display
        self.maxAltitude = maxAltitude
        ## Horizontal position, as distance from the left edge
        # of the canvas
        self.xOffset = xOffset
        ## Minimum Y position of the canvas (lower edge).
        self.minY = minY
        ## Maximum Y position of the canvas (upper edge).
        self.maxY = maxY
        ## Maximum displayed width of any one bucket.
        self.width = width
        ## Whether or not altitudes should be labeled
        self.shouldLabel = shouldLabel
        ## Vertical padding on top and bottom
        self.margin = margin

        ## Size of the largest bucket (most frequent
        # data point) in our range.
        self.maxBucketSize = 1
        if data:
            for y in range(int(self.minAltitude), int(self.maxAltitude) + 1, ALTITUDE_BUCKET_SIZE):
                slot = int(y - self.minAltitude) // ALTITUDE_BUCKET_SIZE
                # MAP - this can crash here when Z-range is small, so bounds-check slot.
                if slot < len(data):
                    self.maxBucketSize = max(self.maxBucketSize, data[slot])


    ## Rescale an altitude to our min and max, so that our min
    # maps to self.minY and our max to self.maxY, modulo our margin
    def scale(self, altitude):
        altitude = float(altitude - self.minAltitude) / (self.maxAltitude - self.minAltitude)
        altitude = altitude * (self.maxY - self.minY - self.margin * 2) + self.minY + self.margin
        return altitude
        


## This class shows a high-level view of where the stage is in Z space. It
# includes the current stage position, hard and soft motion limits, and Z
# tower position information.
class MacroStageZ(macroStageBase.MacroStageBase):
    ## Instantiate the MacroStageZ. 
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        ## Backlink to parent for accessing one of its datastructures
        self.parent = parent
        ## Previous value of the Z safety min; when it changes we have to redo
        # our histograms.
        self.prevZSafety = None

        minZ, maxZ = cockpit.interfaces.stageMover.getHardLimitsForAxis(2)
        ## Total size of the stage's range of motion.
        self.stageExtent = maxZ - minZ
        ## Vertical size of the canvas in microns -- slightly larger than the 
        # stage's range of motion.
        # Note that since our width has no direct meaning, we'll just make it
        # the same as our height, and do everything proportionally.
        self.minY = minZ - self.stageExtent * .05
        self.maxY = maxZ + self.stageExtent * .05
        self.minX = self.minY
        self.maxX = self.maxY
        ## Amount of vertical space to allot to one line of text.
        self.textLineHeight = self.stageExtent * .05
        ## Size of text to draw. Magic numbers ahoy.
        self.textSize = .005
        ## Horizontal position of the main Z position indicator
        self.zHorizOffset = self.maxX - self.stageExtent * .25
        ## Horizontal length of a "marker line" indicating the position of 
        # something on the Z scale.
        self.horizLineLength = self.stageExtent * .1

        self.stepSize = cockpit.interfaces.stageMover.getCurStepSizes()[2]

        ## List of altitudes at which experiments have occurred
        self.experimentAltitudes = []
        ## List of histograms for drawing: one zoomed-out, one zoomed-in.
        self.histograms = []
        ## Dummy histogram that matches the range for the Z macro stage
        self.dummyHistogram = Histogram(self.minY, self.maxY, 
                self.zHorizOffset, self.minY, 
                self.maxY, 0, False, 0)

        self.calculateHistogram()

        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        events.subscribe(events.EXPERIMENT_COMPLETE, self.onExperimentComplete)
        events.subscribe(events.STAGE_TOP_BOTTOM, self.Refresh)
        events.subscribe("soft safety limit", self.onSafetyChange)
        events.subscribe("stage step size", self.onStepSizeChange)
        self.SetToolTip(wx.ToolTip("Double-click to move in Z"))


    ## Calculate the histogram buckets and min/max settings
    # based on self.experimentAltitudes
    def calculateHistogram(self):
        self.experimentAltitudes = list(cockpit.util.userConfig.getValue('experimentAltitudes', 
                                                                         default=[]))
        ## Set of buckets, by altitude, of the experiments
        self.altitudeBuckets = [0 for i in range(int(self.minY),
                int(self.maxY + 1), ALTITUDE_BUCKET_SIZE)]
        for altitude in self.experimentAltitudes:
            slot = int((altitude - self.minY) // ALTITUDE_BUCKET_SIZE)
            if slot < 0 or slot > len(self.altitudeBuckets):
                # This should, of course, be impossible.
                cockpit.util.logger.log.warning("Impossible experiment altitude %f (min %f, max %f)",
                        altitude, self.minY, self.maxY)
            else:
            # bounds check slot
                if slot < len(self.altitudeBuckets):
                    self.altitudeBuckets[slot] += 1


    ## Handle a new experiment completing -- requires us to update our
    # histogram.
    def onExperimentComplete(self, *args):
        # Update histogram data
        self.experimentAltitudes = list(
                cockpit.util.userConfig.getValue('experimentAltitudes', default=[])
        )
        self.experimentAltitudes.append(self.curStagePosition[2])
        cockpit.util.userConfig.setValue('experimentAltitudes', self.experimentAltitudes)
        self.calculateHistogram()


    ## Handle a soft safety limit being changed.
    def onSafetyChange(self, axis, position, isMax):
        if axis != 2 or isMax:
            # We don't care about anything other than the Z safety min.
            return
        if self.prevZSafety is None or self.prevZSafety != position:
            # Update primary histogram display settings
            self.prevZSafety = position


    ## Step sizes have changed, which means we get to redraw.
    # \todo Redrawing *everything* at this stage seems a trifle excessive.
    def onStepSizeChange(self, axis: int, newSize: float) -> None:
        if axis == 2 and self.stepSize != newSize:
            self.stepSize = newSize
            self.shouldForceRedraw = True

    ## Generate the larger of the two histograms.
    def makeBigHistogram(self, altitude):
        minorLimits = cockpit.interfaces.stageMover.getIndividualSoftLimits(2)
        # Add the max range of motion of the first fine-motion controller.
        #And subtract the lower limit if minor controller exisits.
        if(len(minorLimits)>1):
            minorPos= cockpit.interfaces.stageMover.getAllPositions()[1][2]
            histogramMin = altitude-(minorPos-minorLimits[1][0]) - HISTOGRAM_MIN_PADDING
            histogramMax = altitude+(-minorPos+minorLimits[1][1])+HISTOGRAM_MIN_PADDING
        else: 
            histogramMin = altitude-(SECONDARY_HISTOGRAM_SIZE/2.0)- HISTOGRAM_MIN_PADDING
            histogramMax = altitude+(SECONDARY_HISTOGRAM_SIZE/2.0)+HISTOGRAM_MIN_PADDING
        histogram = Histogram(histogramMin, histogramMax, 
                self.zHorizOffset - self.stageExtent * .4, 
                self.minY, self.maxY, 
                self.stageExtent * .2, True, self.stageExtent * .05,
                self.altitudeBuckets)
        if not self.histograms:
            self.histograms.append(histogram)
        else:
            self.histograms[0] = histogram
        wx.CallAfter(self.Refresh)


    ## Overrides the parent function, since we may need to also generate a 
    # histogram based on the new Z position.
    def onMotion(self, axis, position):
        if axis != 2:
            # We only care about the Z axis.
            return
        super().onMotion(axis, position)
        # Ensure there's a histogram to work with based around current pos.
        self.makeBigHistogram(cockpit.interfaces.stageMover.getPosition()[2])
        if self.shouldDraw:
            try:
                motorPos = self.curStagePosition[2]
                if motorPos != self.prevStagePosition[2]:
                    # Check if we need to draw a new mini histogram (that 
                    # scrolls with the stage's Z position).
                    zMin = motorPos - 25
                    zMax = motorPos + 25
                    if zMax < self.histograms[0].maxAltitude:
                        # Stage has entered into the area covered by the 
                        # histogram, so show a zoomed-in version.
                        histogram = Histogram(zMin - MINI_HISTOGRAM_PADDING,
                                zMax + MINI_HISTOGRAM_PADDING,
                                self.zHorizOffset - self.stageExtent * .8, 
                                self.minY, self.maxY, self.stageExtent * .2,
                                False, self.stageExtent * .05, 
                                self.altitudeBuckets)
                        # \todo There must surely be a better way to do this.
                        if len(self.histograms) == 2:
                            self.histograms[1] = histogram
                        else:
                            self.histograms.append(histogram)
                    elif len(self.histograms) > 1:
                        # Don't show the mini histogram since it's not in-range
                        self.histograms = self.histograms[:-1]

            except Exception as e:
                cockpit.util.logger.log.error("Error updating macro stage Z status: %s", e)
                cockpit.util.logger.log.error(traceback.format_exc())
                self.shouldDraw = False

        
    ## Draw the following:
    # - A red line at the current stage height
    # - A purple line at the current Z tower height (or at a ceiling height if
    #   its position is off the scale).
    # - A pair of dotted blue lines for the hard stage motion limits at [4000, 25000]
    # - A dotted green line for the soft stage motion min limit (no max limit)
    # - A red line indicating the stage motion delta
    # - When moving, a blue arrow indicating our direction of motion
    # - A scale indicator
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

            motorPos = self.curStagePosition[2]
            majorPos = cockpit.interfaces.stageMover.getAllPositions()[0][2]
            minorLimits = cockpit.interfaces.stageMover.getIndividualSoftLimits(2)
            # Add the max range of motion of the first fine-motion controller.
            #And subtract the lower limit
            if len(minorLimits) > 1:
                minorPos= cockpit.interfaces.stageMover.getAllPositions()[1][2]
                zMax = majorPos + minorLimits[1][1]
                zMin = majorPos -(minorPos-minorLimits[1][0])
            else:
                zMax = majorPos +(SECONDARY_HISTOGRAM_SIZE/2.0)
                zMax = majorPos -(SECONDARY_HISTOGRAM_SIZE/2.0)
            # Add the max range of motion of the first fine-motion controller.
            if len(minorLimits) > 1:
                zMax = majorPos + minorLimits[1][1]

            # Draw histograms. We do this first so that other lines can be drawn
            # on top.
            self.drawHistograms()
            
            # Draw scale bar
            glColor3f(0, 0, 0)
            glLineWidth(1)
            glBegin(GL_LINES)
            minY, maxY = cockpit.interfaces.stageMover.getHardLimitsForAxis(2)
            scaleX = self.zHorizOffset
            self.scaledVertex(scaleX, minY)
            self.scaledVertex(scaleX, maxY)
            # Draw notches in the scale bar, one every 1mm.
            for scaleY in range(int(minY), int(maxY) + 1000, 1000):
                width = self.stageExtent * .025
                if scaleY % 5000 == 0:
                    width = self.stageExtent * .05
                x1 = scaleX - width / 2
                x2 = scaleX + width / 2
                self.scaledVertex(x1, scaleY)
                self.scaledVertex(x2, scaleY)
            glEnd()
            glLineWidth(1)
            
            glLineWidth(HEIGHT_LINE_WIDTH)

            # Draw spikes for the histogram peaks.
            config = wx.GetApp().Config
            spikeHeight = self.stageExtent * .02
            spikeLength = self.stageExtent * .2
            for altitude in (config['stage'].getfloat('slideAltitude'),
                             config['stage'].getfloat('dishAltitude')):
                glColor3f(0, 0, 0)
                glBegin(GL_POLYGON)
                self.scaledVertex(scaleX, altitude - spikeHeight / 2)
                self.scaledVertex(scaleX - spikeLength, altitude)
                self.scaledVertex(scaleX, altitude + spikeHeight / 2)
                glEnd()
            
            #Draw top and bottom positions of stack in blue.
            self.stackdef = [
                cockpit.interfaces.stageMover.mover.SavedTop,
                cockpit.interfaces.stageMover.mover.SavedBottom,
            ]
            for pos in self.stackdef:
                if pos is not None:
                    self.drawLine(pos, color = (0, 0, 1))

			
            # Draw current stage position
            self.drawLine(motorPos, color = (1, 0, 0),
                    label = str(int(motorPos)), isLabelOnLeft = True)
            
            # Draw hard stage motion limits
            self.drawLine(minY, stipple = 0xAAAA,
                          color = (0, 0, 1), label = '%d' % minY)
            self.drawLine(maxY, stipple = 0xAAAA,
                          color = (0, 0, 1), label = '%d' % maxY)

            # Draw soft stage motion limit
            if self.prevZSafety is not None:
                self.drawLine(self.prevZSafety, stipple = 0x5555,
                        color = (0, .8, 0), label = str(int(self.prevZSafety)))

            # Draw stage motion delta
            glLineWidth(1)
            glColor3f(1, 0, 0)
            glBegin(GL_LINES)
            self.scaledVertex(scaleX + self.horizLineLength / 2, 
                              motorPos + self.stepSize)
            self.scaledVertex(scaleX + self.horizLineLength / 2, 
                              motorPos - self.stepSize)
            glEnd()

            # Draw direction of stage motion, if any
            if abs(motorPos - self.prevStagePosition[2]) > .01:
                delta = motorPos - self.prevStagePosition[2]
                if abs(delta) > macroStageBase.MIN_DELTA_TO_DISPLAY:
                    lineCenterX = scaleX + self.horizLineLength / 2
                    self.drawArrow(
                            (lineCenterX, motorPos), 
                            (0, delta), (0, 0, 1), 
                            self.stageExtent * .15, self.stageExtent * .03
                    )

            glFlush()
            self.SwapBuffers()
            # Set the event, so our refreshWaiter() can update
            # our stage position info.
            self.drawEvent.set()
        except Exception as e:
            cockpit.util.logger.log.error("Error drawing Z macro stage: %s", e)
            traceback.print_exc()
            self.shouldDraw = False


    ## Draw all our histograms
    def drawHistograms(self):
        prevHistogram = self.dummyHistogram
        minY, maxY = cockpit.interfaces.stageMover.getHardLimitsForAxis(2)
        width, height = self.GetClientSize()
        for histogram in self.histograms:
            glColor3f(0, 0, 0)
            glLineWidth(HISTOGRAM_LINE_WIDTH)
            glBegin(GL_LINES)
            for pixelOffset in range(0, height):
                # Convert pixel offset to altitude inside our histogram
                # min/max values
                altitude = float(pixelOffset) / height
                altitude = altitude * (histogram.maxAltitude - histogram.minAltitude) + histogram.minAltitude
                # Map that altitude to a bucket
                bucketIndex = int(altitude - self.minY) // ALTITUDE_BUCKET_SIZE
                if bucketIndex < len(self.altitudeBuckets):
                    count = self.altitudeBuckets[bucketIndex]
                else:
                    continue
                width = int(float(count) / histogram.maxBucketSize * histogram.width)
                drawAltitude = histogram.scale(altitude)
                self.scaledVertex(histogram.xOffset, drawAltitude)
                self.scaledVertex(histogram.xOffset - width, drawAltitude)
            glEnd()
            glLineWidth(1)

            # HACK: For some reason the left edge of the histogram is jagged. 
            # Cover it up.
            glBegin(GL_LINES)
            self.scaledVertex(histogram.xOffset, minY)
            self.scaledVertex(histogram.xOffset, maxY)
            glEnd()

            # Draw histogram min/max
            if histogram.shouldLabel:
                lineHeight = self.stageExtent * .05
                self.drawTextAt((histogram.xOffset + self.stageExtent * .05, 
                        minY - self.textLineHeight / 4),
                        str(int(histogram.minAltitude)), size = self.textSize)
                self.drawTextAt((histogram.xOffset + self.stageExtent * .05, 
                        maxY - self.textLineHeight / 4),
                        str(int(histogram.maxAltitude)), size = self.textSize)
            
            # Draw histogram stage motion delta
            motorPos = self.curStagePosition[2]
            glLineWidth(1)
            glBegin(GL_LINES)
            glColor3f(1, 0, 0)
            self.scaledVertex(histogram.xOffset + self.stageExtent * .01, 
                              histogram.scale(motorPos + self.stepSize))
            self.scaledVertex(histogram.xOffset + self.stageExtent * .01, 
                              histogram.scale(motorPos - self.stepSize))
            glEnd()
            
            # Draw lines showing how the histogram relates to the
            # less zoomed-in view to its left.
            leftBottom = prevHistogram.scale(histogram.minAltitude)
            leftTop = prevHistogram.scale(histogram.maxAltitude)
            glLineWidth(1)
            glColor3f(.5, .5, .5)
            glBegin(GL_LINES)
            self.scaledVertex(prevHistogram.xOffset, leftBottom)
            self.scaledVertex(histogram.xOffset, minY)
            self.scaledVertex(prevHistogram.xOffset, leftTop)
            self.scaledVertex(histogram.xOffset, maxY)
            self.scaledVertex(prevHistogram.xOffset, leftBottom)
            self.scaledVertex(prevHistogram.xOffset, leftTop)
            glEnd()

            prevHistogram = histogram


    ## Draw a horizontal line at the specified altitude.
    def drawLine(self, altitude, lineLength = None,
                 stipple = None, color = (0, 0, 0),
                 width = 2, label = '', isLabelOnLeft = False,
                 shouldLabelMainView = True, shouldLabelHistogram = True):
        if lineLength is None:
            lineLength = self.horizLineLength
        drawAltitude = altitude
        leftEdge = self.zHorizOffset + self.horizLineLength / 2
        rightEdge = self.zHorizOffset - self.horizLineLength / 2
        
        if stipple is not None:
            glEnable(GL_LINE_STIPPLE)
            glLineStipple(3, stipple)
        glColor3fv(color)
        glLineWidth(width)
        glBegin(GL_LINES)
        # Draw on the main view.
        self.scaledVertex(leftEdge, drawAltitude)
        self.scaledVertex(rightEdge, drawAltitude)
        # Draw in the histograms too, if in range
        for histogram in self.histograms:
            if histogram.minAltitude <= altitude <= histogram.maxAltitude:
                # This line should be visible in the histogram.
                xOffset = histogram.xOffset + lineLength / 2.0
                histogramAltitude = histogram.scale(altitude)
                self.scaledVertex(xOffset, histogramAltitude)
                self.scaledVertex(xOffset - lineLength, histogramAltitude)
        glEnd()
        if stipple is not None:
            glDisable(GL_LINE_STIPPLE)
            
        if label:
            glLineWidth(1)
            labelX = rightEdge - self.stageExtent * .01
            if isLabelOnLeft:
                labelX = leftEdge + self.stageExtent * .1
            if shouldLabelMainView:
                # Draw a text label next to the line, in the line's color.
                self.drawTextAt(
                        (labelX, drawAltitude - self.textLineHeight / 4), 
                        label, size = self.textSize, color = color)
            if shouldLabelHistogram:
                # Draw the label for the histograms too.
                for histogram in self.histograms:
                    if histogram.shouldLabel:
                        histogramAltitude = histogram.scale(altitude)
                        histogramLabelX = labelX - histogram.xOffset + self.horizLineLength / 2
                        self.drawTextAt((histogramLabelX,
                                histogramAltitude - self.textLineHeight / 4),
                                label, size = self.textSize, color = color)


    ## Double click moves the stage in Z.
    def OnMouse(self, event):
        if event.LeftDClick():
            clickLoc = event.GetPosition()
            canvasLoc = self.mapClickToCanvas(clickLoc)
            # Map the click location to one of our histograms or to the main scale.
            scale = (self.minY, self.maxY)
            # if we are on the first hist then use the coarest mover if not
            # then use the currently selected one.
            originalMover= cockpit.interfaces.stageMover.mover.curHandlerIndex
            cockpit.interfaces.stageMover.mover.curHandlerIndex = 0

            for histogram in self.histograms:
                if canvasLoc[0] < histogram.xOffset + self.horizLineLength:
                    scale = (histogram.minAltitude, histogram.maxAltitude)
                    # not first hist so revert to current mover whatever that
                    #might be
                    cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover                
                    break # fall through as we have found which
                          # histogram we clicked on
                
            width, height = self.GetClientSize()
            weight = 1. - float(clickLoc[1]) / height
            altitude = (scale[1] - scale[0]) * weight + scale[0]
            zHardMax = cockpit.interfaces.stageMover.getIndividualHardLimits(2)[0][1]
            cockpit.interfaces.stageMover.goToZ(min(zHardMax, altitude))
            #make sure we are back to the expected mover
            cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover



    ## Remap an XY tuple to stage coordinates.
    def mapClickToCanvas(self, loc):
        width, height = self.GetClientSize()
        x = float(width - loc[0]) / width * (self.maxY - self.minY) + self.minY
        y = float(height - loc[1]) / height * (self.maxY - self.minY) + self.minY
        return (x, y)
