import numpy
from OpenGL.GL import *
import FTGL
import traceback
import wx

import depot
import events
import interfaces.stageMover
import util.logger
import util.userConfig

import gui.macroStage.macroStageBase as macroStageBase
import gui.macroStage.macroStageWindow as macroStageWindow
import gui.saveTopBottomPanel
import os
from cockpit import COCKPIT_PATH

## Width of an altitude line.
HEIGHT_LINE_WIDTH = 3

## Distance in microns to include beneath the Z safety min in the histogram
HISTOGRAM_MIN_PADDING = 25
## Thickness of each line in the histogram
HISTOGRAM_LINE_WIDTH = 3
## Size of buckets in microns to use when generating altitude histogram
ALTITUDE_BUCKET_SIZE = 3
## Default height of the histogram, in microns
# (distance between min altitude displayed and max altitude displayed)
DEFAULT_HISTOGRAM_HEIGHT = 200

## Amount, in microns, of padding to add on either end of the mini-histogram
MINI_HISTOGRAM_PADDING = 1

#Size of secondar histogram if no fine motion stage in microns
SECONDARY_HISTOGRAM_SIZE = 50

## Don't bother showing a movement arrow for
# movements smaller than this.
MIN_DELTA_TO_DISPLAY = .01
## Line thickness for the arrow
ARROW_LINE_THICKNESS = 3.5
## Bluntness of the arrowhead (pi/2 == totally blunt)
ARROWHEAD_ANGLE = numpy.pi / 6.0



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
            for y in xrange(int(self.minAltitude), int(self.maxAltitude) + 1, ALTITUDE_BUCKET_SIZE):
                slot = int((y - self.minAltitude) / ALTITUDE_BUCKET_SIZE)
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
class slaveMacroStageZ(wx.glcanvas.GLCanvas):
    ## Instantiate the MacroStageZ.
    def __init__(self, parent, *args, **kwargs):
        wx.glcanvas.GLCanvas.__init__(self, parent, *args, **kwargs)

        ## WX context for drawing.
        self.masterMacroStageZ=macroStageWindow.window.macroStageZ
        self.context = self.masterMacroStageZ.context
        self.haveInitedGL = False
              ## Backlink to parent for accessing one of its datastructures
#        self.parent = parent
        ## Previous value of the Z safety min; when it changes we have to redo
        # our histograms.
        self.prevZSafety = None

        minZ, maxZ = interfaces.stageMover.getHardLimitsForAxis(2)
        ## Total size of the stage's range of motion.
        self.stageExtent = maxZ - minZ

        ##objective offset info to get correct position and limits
        self.objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.listObj = list(self.objective.nameToOffset.keys())
        self.listOffsets = list(self.objective.nameToOffset.values())
        self.offset = self.objective.getOffset()

        ## (X, Y, Z) vector describing the stage position as of the last
        # time we drew ourselves. We need this to display motion deltas.
        self.prevStagePosition = numpy.zeros(3)
        ## As above, but for the current position.
        self.curStagePosition = numpy.zeros(3)
        ## Event used to indicate when drawing is done, so we can update
        # the above.
        #self.drawEvent = threading.Event()
        self.shouldDraw = True
        ## Font for drawing text
        try:
            path = os.path.join(COCKPIT_PATH, 'resources',
                                'fonts', 'GeosansLight.ttf')
            self.font = FTGL.TextureFont(path)
            self.font.FaceSize(18)
        except Exception, e:
            print "Failed to make font:",e

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

        ## List of altitudes at which experiments have occurred
        self.experimentAltitudes = []
        ## List of histograms for drawing: one zoomed-out, one zoomed-in.
        self.histograms = []
        ## Dummy histogram that matches the range for the Z macro stage
        self.dummyHistogram = Histogram(self.minY, self.maxY,
                self.zHorizOffset, self.minY,
                self.maxY, 0, False, 0)

        self.calculateHistogram()

        #wx events to update display.
        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_SIZE, lambda event: event)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: event) # Do nothing, to avoid flashing
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        events.subscribe("soft safety limit", self.onSafetyChange)
        events.subscribe("stage position", self.onMotion)
        events.subscribe("stage step size", self.onStepSizeChange)
        events.subscribe("experiment complete", self.onExperimentComplete)
        events.subscribe("soft safety limit", self.onSafetyChange)
        self.SetToolTip(wx.ToolTip("Double-click to move in Z"))

    ## Set up some set-once things for OpenGL.
    def initGL(self):
        (self.width, self.height) = self.GetClientSize()
        self.SetCurrent(self.context)
        glClearColor(1.0, 1.0, 1.0, 0.0)

    ## Safety limits have changed, which means we need to force a refresh.
    # \todo Redrawing everything just to tackle the safety limits is a bit
    # excessive.
    def onSafetyChange(self, axis, value, isMax):
        # We only care about the Z axis.
        if axis is 2:
            wx.CallAfter(self.Refresh)


    ## Calculate the histogram buckets and min/max settings
    # based on self.experimentAltitudes
    def calculateHistogram(self):
        self.experimentAltitudes = list(util.userConfig.getValue('experimentAltitudes',
                default = [], isGlobal = True))
        ## Set of buckets, by altitude, of the experiments
        self.altitudeBuckets = [0 for i in range(int(self.minY),
                int(self.maxY + 1), ALTITUDE_BUCKET_SIZE)]
        for altitude in self.experimentAltitudes:
            slot = int((altitude - self.minY) / ALTITUDE_BUCKET_SIZE)
            if slot < 0 or slot > len(self.altitudeBuckets):
                # This should, of course, be impossible.
                util.logger.log.warn("Impossible experiment altitude %f (min %f, max %f)",
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
                util.userConfig.getValue('experimentAltitudes', default = [], isGlobal = True)
        )
        self.experimentAltitudes.append(self.curStagePosition[2])
        util.userConfig.setValue('experimentAltitudes', self.experimentAltitudes, isGlobal=True)
        self.calculateHistogram()


    ## Handle a soft safety limit being changed.
    def onSafetyChange(self, axis, position, isMax):
        if axis != 2 or isMax:
            # We don't care about anything other than the Z safety min.
            return
        if self.prevZSafety is None or self.prevZSafety != position:
            # Update primary histogram display settings
            self.prevZSafety = position


    ## Generate the larger of the two histograms.
    def makeBigHistogram(self, altitude):
        minorLimits = interfaces.stageMover.getIndividualSoftLimits(2)
        # Add the max range of motion of the first fine-motion controller.
        #And subtract the lower limit if minor controller exisits.
        if(len(minorLimits)>1):
            minorPos= interfaces.stageMover.getAllPositions()[1][2]
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

    ##On setp size change just need to redraw.
    def onStepSizeChange(self,axis,newSize):
        if axis is 2:
            self.Refresh()


    ## Overrides the parent function, since we may need to also generate a
    # histogram based on the new Z position.
    def onMotion(self, axis, position):
        if axis != 2:
            # We only care about the Z axis.
            return
        self.curStagePosition[axis] = position
        # Ensure there's a histogram to work with based around current pos.
        self.makeBigHistogram(interfaces.stageMover.getPosition()[2])
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
                self.Refresh
            except Exception, e:
                util.logger.log.error("Error updating macro stage Z status: %s", e)
                util.logger.log.error(traceback.format_exc())
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

            glViewport(0, 0, self.width, self.height)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            motorPos = self.curStagePosition[2]
            majorPos = interfaces.stageMover.getAllPositions()[0][2]
            minorLimits = interfaces.stageMover.getIndividualSoftLimits(2)
            # Add the max range of motion of the first fine-motion controller.
            #And subtract the lower limit
            if len(minorLimits) > 1:
                minorPos= interfaces.stageMover.getAllPositions()[1][2]
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
            minY, maxY = interfaces.stageMover.getHardLimitsForAxis(2)
            scaleX = self.zHorizOffset
            self.scaledVertex(scaleX, minY)
            self.scaledVertex(scaleX, maxY)
            # Draw notches in the scale bar, one every 1mm.
            for scaleY in xrange(minY, maxY + 1000, 1000):
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
            configurator = depot.getHandlersOfType(depot.CONFIGURATOR)[0]
            spikeHeight = self.stageExtent * .02
            spikeLength = self.stageExtent * .2
            for altitude in [configurator.getValue('slidealtitude'),
                    configurator.getValue('dishaltitude')]:
                glColor3f(0, 0, 0)
                glBegin(GL_POLYGON)
                self.scaledVertex(scaleX, altitude - spikeHeight / 2)
                self.scaledVertex(scaleX - spikeLength, altitude)
                self.scaledVertex(scaleX, altitude + spikeHeight / 2)
                glEnd()

            #Draw top and bottom positions of stack in blue.
            self.stackdef=[gui.saveTopBottomPanel.savedTop,
                          gui.saveTopBottomPanel.savedBottom]
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
            #if self.prevZSafety is not None:
            #    self.drawLine(self.prevZSafety, stipple = 0x5555,
            #            color = (0, .8, 0), label = str(int(self.prevZSafety)))

            # Draw stage motion delta
            stepSize = interfaces.stageMover.getCurStepSizes()[2]
            if stepSize is not None:
                glLineWidth(1)
                glColor3f(1, 0, 0)
                glBegin(GL_LINES)
                self.scaledVertex(scaleX + self.horizLineLength / 2,
                        motorPos + stepSize)
                self.scaledVertex(scaleX + self.horizLineLength / 2,
                        motorPos - stepSize)
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
            self.prevStagePosition = self.curStagePosition
            glFlush()
            self.SwapBuffers()
            # Set the event, so our refreshWaiter() can update
            # our stage position info.
#            self.drawEvent.set()
        except Exception, e:
            util.logger.log.error("Error drawing Z macro stage: %s", e)
            traceback.print_exc()
            self.shouldDraw = False


    ## Draw all our histograms
    def drawHistograms(self):
        prevHistogram = self.dummyHistogram
        minY, maxY = interfaces.stageMover.getHardLimitsForAxis(2)
        for histogram in self.histograms:
            glColor3f(0, 0, 0)
            glLineWidth(HISTOGRAM_LINE_WIDTH)
            glBegin(GL_LINES)
            for pixelOffset in xrange(0, self.height):
                # Convert pixel offset to altitude inside our histogram
                # min/max values
                altitude = float(pixelOffset) / self.height
                altitude = altitude * (histogram.maxAltitude - histogram.minAltitude) + histogram.minAltitude
                # Map that altitude to a bucket
                bucketIndex = int((altitude - self.minY) / ALTITUDE_BUCKET_SIZE)
                if bucketIndex < len(self.altitudeBuckets):
                    count = self.altitudeBuckets[bucketIndex]
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
            stepSize = interfaces.stageMover.getCurStepSizes()[2]
            if stepSize is not None:
                motorPos = self.curStagePosition[2]
                glLineWidth(1)
                glBegin(GL_LINES)
                glColor3f(1, 0, 0)
                self.scaledVertex(histogram.xOffset + self.stageExtent * .01,
                        histogram.scale(motorPos + stepSize))
                self.scaledVertex(histogram.xOffset + self.stageExtent * .01,
                        histogram.scale(motorPos - stepSize))
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

    def scaledVertex(self, x, y, shouldReturn = False):
        newX = -1 * ((x - self.minX) / float(self.maxX - self.minX) * 2 - 1)
        newY = (y - self.minY) / float(self.maxY - self.minY) * 2 - 1
        if shouldReturn:
            return (newX, newY)
        else:
            glVertex2f(newX, newY)


    ## Draw some text at the specified location
    def drawTextAt(self, loc, text, size, color = (0, 0, 0)):
        loc = self.scaledVertex(loc[0], loc[1], True)
        aspect = float(self.height) / self.width
        glPushMatrix()
        glTranslatef(loc[0], loc[1], 0)
        glScalef(size * aspect, size, size)
        glColor3fv(color)
        self.font.Render(text)
        glPopMatrix()

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
                labelX = leftEdge + self.stageExtent * .12
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
            originalMover= interfaces.stageMover.mover.curHandlerIndex
            interfaces.stageMover.mover.curHandlerIndex = 0

            for histogram in self.histograms:
                if canvasLoc[0] < histogram.xOffset + self.horizLineLength:
                    scale = (histogram.minAltitude, histogram.maxAltitude)
                    # not first hist so revert to current mover whatever that
                    #might be
                    interfaces.stageMover.mover.curHandlerIndex = originalMover
                    break # fall through as we have found which
                          # histogram we clicked on


            weight = float(self.height - clickLoc[1]) / self.height
            altitude = (scale[1] - scale[0]) * weight + scale[0]
            # Spurious clicks are problematic on a touchscreen. Rather than
            # moving directly to the clicked position, step in that direction
            # to avoid large moves that may cause damage.
            if altitude > interfaces.stageMover.getAllPositions()[-1]:
                direction = (0, 0, -1)
            else:
                direction = (0, 0, 1)
            interfaces.stageMover.step(direction)
            #make sure we are back to the expected mover
            interfaces.stageMover.mover.curHandlerIndex = originalMover


    ## Remap an XY tuple to stage coordinates.
    def mapClickToCanvas(self, loc):
        x = float(self.width - loc[0]) / self.width * (self.maxY - self.minY) + self.minY
        y = float(self.height - loc[1]) / self.height * (self.maxY - self.minY) + self.minY
        return (x, y)



# ## This class shows a key for the MacroStageZ. It's a separate class
# # primarily because of layout issues -- it's wider than the MacroStageZ itself,
# # and therefore needs to have its own canvas.
# class MacroStageZKey(macroStageBase.MacroStageBase):
#     ## Instantiate the MacroStageZKey.
#     def __init__(self, parent, *args, **kwargs):
#         macroStageBase.MacroStageBase.__init__(self, parent, *args, **kwargs)
#         ## Still no idea how this relates to anything, but this value seems
#         # to work well.
#         self.textSize = .03
#         self.xExtent = self.maxX - self.minX
#         self.yExtent = self.maxY - self.minY
#         ## Amount of space to allocate per line of text.
#         self.textLineHeight = self.yExtent * .2
#         ## X offset for text.
#         self.xOffset = self.xExtent * .9
#         ## Y offset for text. Ditto.
#         self.yOffset = self.yExtent * .75


#     ## Draw the key
#     def onPaint(self, event = None):
#         if not self.shouldDraw:
#             return
#         try:
#             if not self.haveInitedGL:
#                 self.initGL()
#                 self.haveInitedGL = True

#             dc = wx.PaintDC(self)
#             self.SetCurrent(self.context)

#             glViewport(0, 0, self.width, self.height)

#             glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
#             glLineWidth(1)

#             # Draw textual position coordinates.
#             positions = interfaces.stageMover.getAllPositions()
#             positions = [p[2] for p in positions]
#             stepSize = interfaces.stageMover.getCurStepSizes()[2]
#             self.drawStagePosition('Z:', positions,
#                     interfaces.stageMover.getCurHandlerIndex(), stepSize,
#                     (self.xOffset, self.yOffset), self.xExtent * .26,
#                     self.xExtent * .05, self.textSize)

#             glFlush()
#             self.SwapBuffers()
#             # Set the event, so our refreshWaiter() can update
#             # our stage position info.
#             self.drawEvent.set()
#         except Exception, e:
#             util.logger.log.error("Error drawing Z macro stage key: %s", e)
#             traceback.print_exc()
#             self.shouldDraw = False
