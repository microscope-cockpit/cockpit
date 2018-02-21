import FTGL
import numpy
import os
from OpenGL.GL import *
import threading
import time
import wx

import events
import interfaces.stageMover
import util.logger
import depot

from cockpit import COCKPIT_PATH

PI = 3.1415926

## @package gui.macroStage
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
            path = os.path.join(COCKPIT_PATH, 'resources',
                                'fonts', 'GeosansLight.ttf')
            self.font = FTGL.TextureFont(path)
            self.font.FaceSize(18)
        except Exception, e:
            print "Failed to make font:",e

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
        self.redrawTimerThread = threading.Thread(target = self.refreshWaiter)
        self.redrawTimerThread.start()

        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_SIZE, lambda event: event)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: event) # Do nothing, to avoid flashing
        events.subscribe("stage position", self.onMotion)
        events.subscribe("stage step size", self.onStepSizeChange)
        events.subscribe("stage step index", self.onStepIndexChange)


    ## Set up some set-once things for OpenGL.
    def initGL(self):
        (self.width, self.height) = self.GetClientSize()
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
        self.font.Render(text)
        glPopMatrix()


    ## Draw stage position information.
    # \param label Text label to draw at the front.
    # \param positions A list of floats indicating the position of the various
    #        stage movers.
    # \param highlightIndex Index into the above indicating which position
    #        should be highlighted (to indicate keypad control). 
    # \param stepSize Float that will be drawn afterwards showing the current
    #        step size.
    # \param drawLoc (X, Y) tuple indicating the position at which to draw the 
    #        text.
    # \param spacer Amount of space to put between each element.
    # \param labelSpacer Amount of space to dedicate to the label.
    # \param textSize Size of text to draw.
    def drawStagePosition(self, label, positions, highlightIndex, stepSize, 
            drawLoc, spacer, labelSpacer, textSize):
        # Make the label bigger, since it really needs to call attention to 
        # itself.
        self.drawTextAt(drawLoc, label, size = textSize * 1.25)
        for i, pos in enumerate(positions):
            if pos is None:
                # No positioning for this axis.
                continue
            color = (0, 0, 0)
            if i == highlightIndex:
                color = (0, .5, 0)
            self.drawTextAt((drawLoc[0] - labelSpacer - i * spacer, drawLoc[1]),
                "%5.2f" % pos, textSize, color)

        self.drawTextAt((drawLoc[0] - labelSpacer - len(positions) * spacer,
                drawLoc[1]),
                "step: %4.2fum" % stepSize, size = textSize)


    ## Draw a circle of radius r centred on x0, y0 with n segments.
    def drawScaledCircle(self, x0, y0, r, n):
        dTheta = 2. * PI / n
        cosTheta = numpy.cos(dTheta)
        sinTheta = numpy.sin(dTheta)
        x = r
        y = 0.

        glBegin(GL_LINE_LOOP)
        for i in xrange(n):
            self.scaledVertex(x0 + x, y0 + y)
            xOld = x
            x = cosTheta * x - sinTheta * y
            y = sinTheta * xOld + cosTheta * y
        glEnd()


    ## Draw a rectangle centred on x0, y0 of width w and height h.
    def drawScaledRectangle(self, x0, y0, w, h):
        dw = w / 2.
        dh = h / 2.
        ps = [(x0-dw, y0-dh),
              (x0+dw, y0-dh),
              (x0+dw, y0+dh),
              (x0-dw, y0+dh)]

        glBegin(GL_LINE_LOOP)
        for i in xrange(-1, 4):
            self.scaledVertex(*ps[i])
        glEnd()
