import numpy
from OpenGL.GL import *
import traceback
import wx

import events
import gui.mosaic.window
import interfaces.stageMover
import util.logger

import macroStageBase

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

        hardLimits = interfaces.stageMover.getHardLimits()
        self.minX, self.maxX = hardLimits[0]
        self.minY, self.maxY = hardLimits[1]
        ## X extent of the stage, in microns.
        self.stageWidth = self.maxX - self.minX
        ## Y extent of the stage, in microns.
        self.stageHeight = self.maxY - self.minY
        ## Max of X or Y stage extents.
        self.maxExtent = max(self.stageWidth, self.stageHeight)
        ## X and Y view extent.
        if self.stageHeight > self.stageWidth:
            self.viewExtent = 1.2 * self.stageHeight
            self.viewDeltaY = self.stageHeight * 0.1
        else:
            self.viewExtent = 1.05 * self.stageWidth
            self.viewDeltaY = self.stageHeight * 0.05
        # Push out the min and max values a bit to give us some room around
        # the stage to work with. In particular we need space below the display
        # to show our legend.
        self.centreX = ((self.maxX - self.minX) / 2) + self.minX
        self.centreY = ((self.maxY - self.minY) / 2) + self.minY
        self.minX = self.centreX - self.viewExtent / 2
        self.maxX = self.centreX + self.viewExtent / 2
        self.minY = self.centreY - self.viewExtent / 2 - self.viewDeltaY
        self.maxY = self.centreY + self.viewExtent / 2 - self.viewDeltaY

        ## Amount of vertical space, in stage coordinates, to allot to one
        # line of text.
        self.textLineHeight = self.viewExtent * .05
        ## Size of text to draw. I confess I don't really understand how this
        # corresponds to anything, but it seems to work out.
        self.textSize = .004

        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftClick)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDoubleClick)
        self.Bind(wx.EVT_RIGHT_UP, self.OnRightClick)
        self.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDoubleClick)
        events.subscribe("soft safety limit", self.onSafetyChange)
        events.subscribe('objective change', self.onObjectiveChange)
        self.SetToolTip(wx.ToolTip("Left double-click to move the stage. " +
                "Right click for gotoXYZ and double-click to toggle displaying of mosaic " +
                "tiles."))


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

            glViewport(0, 0, self.width, self.height)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            squareOffsets = [(0, 0), (0, 1), (1, 1), (1, 0)]
            stepSizes = interfaces.stageMover.getCurStepSizes()[:2]

            # Draw hard stage motion limits
            hardLimits = interfaces.stageMover.getHardLimits()[:2]
            # Rearrange limits to (x, y) tuples.
            hardLimits = zip(hardLimits[0], hardLimits[1])
            #Loop over objective offsets to draw limist in multiple colours.
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
                    self.scaledVertex(hardLimits[xIndex][0]-offset[0],
                                      hardLimits[yIndex][1]+offset[1])
                glEnd()
                glDisable(GL_LINE_STIPPLE)

                # Draw soft stage motion limits -- a dotted box, solid black
                # corners, and coordinates. If we're currently setting safeties,
                # then the second corner is the current mouse position.
                safeties = interfaces.stageMover.getSoftLimits()[:2]
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
                    self.scaledVertex(x-offset[0], y+offset[1])
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
                    self.scaledVertex(vx-offset[0], vy+offset[1])
                    self.scaledVertex(secondVertex[0]-offset[0],
                                      secondVertex[1]+offset[1])
                glEnd()
                glLineWidth(1)
            # Now the coordinates. Only draw them if the soft limits aren't
            # the hard limits, to avoid clutter.
            hardLimits = interfaces.stageMover.getHardLimits()[:2]
            if safeties != hardLimits:
                for i, (dx, dy) in enumerate([(4000, -700), (2000, 400)]):
                    x = softLimits[i][0]
                    y = softLimits[i][1]
                    self.drawTextAt((x + dx, y + dy),
                            "(%d, %d)" % (x, y), size = self.textSize * .75)

            glDisable(GL_LINE_STIPPLE)

            # Draw device-specific primitives.
            glEnable(GL_LINE_STIPPLE)
            glLineStipple(1, 0xAAAA)
            glColor3f(0.4, 0.4, 0.4)
            primitives = interfaces.stageMover.getPrimitives()
            for p in primitives:
                if p.type in ['c', 'C']:
                    # circle: x0, y0, radius
                    self.drawScaledCircle(p.data[0], p.data[1],
                                          p.data[2], CIRCLE_SEGMENTS)
                if p.type in ['r', 'R']:
                    # rectangle: x0, y0, width, height
                    self.drawScaledRectangle(*p.data)
            glDisable(GL_LINE_STIPPLE)
            #Draw possibloe stage positions for current objective
            obj = self.objective.curObjective
            offset=self.objective.nameToOffset.get(obj)
            colour=self.objective.nameToColour.get(obj)
            glLineWidth(2)
            # Draw stage position
            motorPos = self.curStagePosition[:2]
            squareSize = self.maxExtent * .025
            glColor3f(*colour)
            glBegin(GL_LINE_LOOP)
            for (x, y) in squareOffsets:
                self.scaledVertex(motorPos[0]-offset[0] +
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
                self.scaledVertex(motorPos[0] - offset[0], motorPos[1] - offset[1])
                self.scaledVertex(motorPos[0] + offset[0], motorPos[1] + offset[1])
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
            self.scaledVertex(motorPos[0]-self.offset[0],
                              motorPos[1]+self.offset[1])
            glEnd()

            # Draw scale bar
            glColor3f(0, 0, 0)
            glLineWidth(1)
            glBegin(GL_LINES)
            yOffset = self.minY + 0.9 * (self.viewDeltaY + 0.5 * (self.viewExtent - self.stageHeight))
            self.scaledVertex(hardLimits[0][0], yOffset)
            self.scaledVertex(hardLimits[0][1], yOffset)
            # Draw notches in the scale bar every 1mm.
            for scaleX in xrange(int(hardLimits[0][0]), int(hardLimits[0][1]) + 1000, 1000):
                width = self.viewExtent * .015
                if scaleX % 5000 == 0:
                    width = self.viewExtent * .025
                y1 = yOffset - width / 2
                y2 = yOffset + width / 2
                self.scaledVertex(scaleX, y1)
                self.scaledVertex(scaleX, y2)
            glEnd()
            glLineWidth(1)

            # Draw stage coordinates. Use a different color for the mover
            # currently under keypad control.
            coordsLoc = (self.maxX - self.viewExtent * .05,
                    self.minY + self.viewExtent * .1)
            allPositions = interfaces.stageMover.getAllPositions()
            curControl = interfaces.stageMover.getCurHandlerIndex()
            for axis in [0, 1]:
                step = stepSizes[axis]
                if stepSizes[axis] is None:
                    step = 0
                positions = [p[axis] for p in allPositions]
                self.drawStagePosition(['X:', 'Y:'][axis],
                        positions, curControl, step,
                        (coordsLoc[0], coordsLoc[1] - axis * self.textLineHeight),
                        self.viewExtent * .25, self.viewExtent * .05,
                        self.textSize)

            events.publish('macro stage xy draw', self)

            glFlush()
            self.SwapBuffers()
            # Set the event, so our refreshWaiter() can update
            # our stage position info.
            self.drawEvent.set()
        except Exception, e:
            util.logger.log.error("Exception drawing XY macro stage: %s", e)
            util.logger.log.error(traceback.format_exc())
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
            interfaces.stageMover.setSoftMin(0, x1)
            interfaces.stageMover.setSoftMax(0, x2)
            # Add 1 to prevent rounding issues relative to current position.
            interfaces.stageMover.setSoftMin(1, y1 + 1)
            interfaces.stageMover.setSoftMax(1, y2 + 1)
            self.amSettingSafeties = False
            self.firstSafetyMousePos = None
            self.Refresh()


    ## Moved the mouse. Record its position
    def OnMouseMotion(self, event):
        self.lastMousePos = self.remapClick(event.GetPosition())
        if self.amSettingSafeties and self.firstSafetyMousePos:
            # Need to redraw to show the new safeties.
            self.Refresh()


    ## Clicked the left mouse button. Set safeties if we're in that mode.
    def OnLeftClick(self, event):
        if self.amSettingSafeties:
            safeLoc = self.remapClick(event.GetPosition())
            self.setXYLimit(safeLoc)


    ## Double-clicked the left mouse button. Move to the clicked location.
    def OnLeftDoubleClick(self, event):
        originalMover= interfaces.stageMover.mover.curHandlerIndex
        #Quick hack to get deepsim working need to check if we can do it
        #properly.  Should really check to see if we can move, and by that
        #distance with exisiting mover
        interfaces.stageMover.mover.curHandlerIndex = 0

        interfaces.stageMover.goToXY(self.remapClick(event.GetPosition()))

        #make sure we are back to the expected mover
        interfaces.stageMover.mover.curHandlerIndex = originalMover

    def OnRightClick(self, event):
        position = interfaces.stageMover.getPosition()
        values=gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                self.GetParent(),
                "Go To XYZ",('X','Y','Z'),
                position,
                atMouse=True)
        newPos=[float(values[0]),float(values[1]),float(values[2])]
#Work out if we will be ouside the limits of the current stage
        posDelta = [newPos[0]-position[0],newPos[1]-position[1],newPos[2]-position[2]]
        originalHandlerIndex = interfaces.stageMover.mover.curHandlerIndex
        currentHandlerIndex = originalHandlerIndex
        allPositions=interfaces.stageMover.getAllPositions()
        for axis in range(3):
            if (posDelta[axis]**2 > .001 ):
                    limits = interfaces.stageMover.getIndividualHardLimits(axis)
                    currentpos = allPositions[currentHandlerIndex][axis]
                    if  ((currentpos == None ) or  # no handler on this axis.
                          (currentpos + posDelta[axis]<(limits[currentHandlerIndex][0])) or # off bottom
                          (currentpos + posDelta[axis]>(limits[currentHandlerIndex][1]))): #off top
                        currentHandlerIndex -= 1 # go to a bigger handler index
                    if currentHandlerIndex<0:
                        return False
        interfaces.stageMover.mover.curHandlerIndex = currentHandlerIndex
        interfaces.stageMover.goTo(newPos)
        interfaces.stageMover.mover.curHandlerIndex = originalHandlerIndex
        return True


    ## Right-clicked the mouse. Toggle drawing of the mosaic tiles
    def OnRightDoubleClick(self, event):
        self.shouldDrawMosaic = not self.shouldDrawMosaic


    ## Remap a click location from pixel coordinates to realspace coordinates
    def remapClick(self, clickLoc):
        x = float(self.width - clickLoc[0]) / self.width * (self.maxX - self.minX) + self.minX
        y = float(self.height - clickLoc[1]) / self.height * (self.maxY - self.minY) + self.minY
        return [x+self.offset[0], y-self.offset[1]]


    ## Switch mode so that clicking sets the safeties
    def setSafeties(self, event = None):
        self.amSettingSafeties = True

    ## Refresh display on objective change
    def onObjectiveChange(self, name, pixelSize, transform, offset, **kwargs):
        self.offset = offset
        self.Refresh()


