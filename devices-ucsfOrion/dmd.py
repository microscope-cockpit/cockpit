import depot
import device
import events
import gui.guiUtils
import gui.mosaic.tile
import gui.toggleButton
import interfaces.stageMover

import ctypes
import numpy
from OpenGL.GL import *
import os
import time
import wx
import wx.glcanvas

CLASS_NAME = 'DMDDevice'


## Width in pixels of the button bar.
BUTTON_WIDTH = 100



## This Device code just exists to create a UI for interacting with the
# Mosaic DMD.
class DMDDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Path to the file that is polled to update the DMD pattern.
        self.path = 'C:\Users\Administrator\Desktop\Release\THEFILE.txt'
        ## Window for the DMD control.
        self.window = None
        ## Panel containing the widgets in the DMD control.
        self.panel = None
        ## Height of a button in the DMD control.
        self.buttonHeight = 0
        ## Canvas for displaying the DMD pattern.
        self.canvas = None
        ## Last known mouse position.
        self.prevMousePos = None
        ## Array of pixel values representing the DMD pattern.
        self.data = None
        ## Maps Sites to array values for the DMD.
        self.siteToPattern = {}


    def initialize(self):
        self.loadArray()
        events.subscribe('arrive at site', self.onGoToSite)


    def makeUI(self, parent):
        button = gui.toggleButton.ToggleButton(parent = parent, label = "DMD",
                size = (120, 50))
        button.Bind(wx.EVT_LEFT_DOWN, self.showWindow)
        return button


    ## Make the DMD control window, or bring it to the front if it already
    # exists.
    def showWindow(self, event = None):
        if self.window is not None:
            # Window still exists; just bring it to the front
            self.window.Raise()
            return
        self.window = wx.Frame(parent = None, title = "DMD pattern display")
        self.window.Bind(wx.EVT_CLOSE, self.onClose)
        self.panel = wx.Panel(self.window)
        sizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        for label, action in [
                ('Write to DMD', lambda event: self.writeArray(self.data)),
                ('Reload from DMD', lambda event: self.loadArray()),
                ('Clear to white', lambda event: self.clear(1)),
                ('Clear to black', lambda event: self.clear(0)),
                ('Record for site', lambda event: self.recordForSite())]:
            button = wx.Button(self.panel, -1, label,
                    size = (BUTTON_WIDTH, -1))
            button.Bind(wx.EVT_BUTTON, action)
            buttonSizer.Add(button, 0, wx.EXPAND)
            self.buttonHeight = button.GetSize()[1]
        sizer.Add(buttonSizer)
        self.canvas = DMDCanvas(self.panel, self.data)
        self.canvas.SetToolTipString("Left-click to draw white rectangles, right-click to draw black ones. Hold shift to draw polygons.")
        ## Propagate size events through to the canvas.
        self.window.Bind(wx.EVT_SIZE, self.onSize)
        self.canvas.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        sizer.Add(self.canvas, 1)
        self.panel.SetSizerAndFit(sizer)
        self.window.SetClientSize((800, 600 + self.buttonHeight))
        self.window.Show()


    ## The window was closed; invalidate it.
    def onClose(self, event):
        self.window = None
        event.Skip()


    ## The window has changed size; resize the canvas to suit.
    def onSize(self, event):
        width, height = self.window.GetClientSizeTuple()
        self.canvas.SetSize((width, height - self.buttonHeight))
        event.Skip()


    ## A mouse event was posted to the canvas. Left/right clicking starts or
    # ends drawing rectangles; general mouse motion updates the vertices.
    def onMouse(self, event):
        curPos = self.canvas.remapPosition(event.GetPosition())
        self.canvas.rectVert2 = curPos
        minX = minY = maxX = maxY = None
        if self.prevMousePos is not None:
            minX = min(self.prevMousePos[0], curPos[0])
            minY = min(self.prevMousePos[1], curPos[1])
            maxX = max(self.prevMousePos[0], curPos[0])
            maxY = max(self.prevMousePos[1], curPos[1])
        # Set a different value depending on which button was used.
        value = 0
        rectColor = (255, 0, 0)
        if event.LeftDown():
            value = 1
            rectColor = (0, 0, 255)
        if event.LeftDown() or event.RightDown():
            if event.ShiftDown():
                # Shift is held; draw a polygon.
                self.canvas.polygonPoints.append(curPos)
                self.canvas.rectColor = rectColor
            elif self.canvas.polygonPoints:
                # Draw a polygon, including the most recent point.
                self.canvas.polygonPoints.append(curPos)
                self.rasterizePolygon(self.canvas.polygonPoints)
                self.canvas.setDisplay(self.data)
                self.canvas.polygonPoints = []
                self.prevMousePos = None
                self.canvas.rectColor = None
            elif self.prevMousePos is not None:
                # Draw a rectangle from the previous position to the new one.
                self.data[minY : maxY, minX : maxX] = value
                self.canvas.setDisplay(self.data)
                self.prevMousePos = None
                self.canvas.rectColor = None
            else:
                # Save the current mouse position for future rectangle drawing.
                self.prevMousePos = curPos
                self.canvas.rectVert1 = curPos
                self.canvas.rectColor = rectColor
        self.canvas.Refresh()


    ## Convert the provided list of points into a rasterized polygon.
    # Function adapted from http://en.wikipedia.org/wiki/Even-odd_rule
    def rasterizePolygon(self, points):
        # Force a loop.
        points.append(points[0])
        for y in xrange(self.data.shape[0]):
            for x in xrange(self.data.shape[1]):
                doesIntersect = False
                for i, (px, py) in enumerate(points[:-1]):
                    nx, ny = points[i + 1]
                    # HACK: avoid division-by-zero errors.
                    if ny == py:
                        ny += 1
                    if  (((py > y) != (ny > y)) and 
                            (x < (nx - px) * (y - py) / (ny - py) + px)):
                        doesIntersect = not doesIntersect
                if doesIntersect:
                    self.data[(y, x)] = self.canvas.rectColor == (255, 0, 0)


    ## Write a new pattern to the DMD.
    def writeArray(self, data):
        assert(data.shape == (600, 800))
        handle = open(self.path, 'w')
        for row in data:
            handle.write(" ".join(map(str, row)) + "\n")
        handle.close()


    ## Write a single value to the entire array.
    def clear(self, newVal):
        self.data[:] = newVal
        self.canvas.setDisplay(self.data)


    ## Load the current pattern from the DMD.
    def loadArray(self):
        handle = open(self.path, 'r')
        lines = handle.readlines()
        handle.close()
        array = []
        for row in lines:
            array.append(map(int, row.split(" ")))
        self.data = numpy.array(array, dtype = numpy.uint16)
        if self.canvas is not None:
            self.canvas.setDisplay(self.data)


    ## Associate our current pattern with a specific site.
    def recordForSite(self):
        sites = interfaces.stageMover.getAllSites()
        choices = ['%d: %s' % (site.uniqueID, ['%d' % p for p in site.position]) for site in sites]
        menu = wx.Menu()
        def setForSite(i):
            self.siteToPattern[sites[i]] = numpy.array(self.data)
        for i, choice in enumerate(choices):
            menu.Append(i + 1, choice)
            wx.EVT_MENU(self.panel, i + 1,
                    lambda event, i = i: setForSite(i))
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    ## Arrived at a site; load our pattern, if any.
    def onGoToSite(self, site):
        pattern = self.siteToPattern.get(site, None)
        if pattern is not None and numpy.any(pattern != self.data):
            self.data[:] = pattern
            self.canvas.setDisplay(self.data)
            self.writeArray(self.data)



## Allows drawing on the canvas, to translate to modifying the DMD pattern.
class DMDCanvas(wx.glcanvas.GLCanvas):
    def __init__(self, parent, displayData):
        wx.glcanvas.GLCanvas.__init__(self, parent)
        ## Array of pixels we are currently drawing.
        self.curDisplay = displayData
        ## gui.mosaic.tile.Tile instance for our pixels.
        self.tile = None
        ## WX context for drawing.
        self.context = wx.glcanvas.GLContext(self)
        ## Whether or not we've initialized OpenGL.
        self.haveInitedGL = False
        ## Whether or not we should try to draw.
        self.shouldDraw = True
        ## Whether or not we should force the tile to refresh.
        self.shouldRefresh = True

        ## Color of the rectangle we are drawing, if any.
        self.rectColor = None
        ## First vertex of the rectangle we are drawing, if any.
        self.rectVert1 = None
        ## Second vertex of the rectangle we are drawing, if any.
        self.rectVert2 = None
        ## List of previous mouse positions when drawing polygons.
        self.polygonPoints = []

        ## Min/max X/Y values.
        self.minX, self.minY, self.maxX, self.maxY = 0, 0, displayData.shape[1], displayData.shape[0]

        ## Width and height of the canvas.
        self.width = self.height = None

        wx.EVT_PAINT(self, self.onPaint)
        wx.EVT_SIZE(self, lambda *args: None)
        wx.EVT_ERASE_BACKGROUND(self, lambda *args: None)

        self.setDisplay(displayData)


    def initGL(self,):
        self.width, self.height = self.GetClientSizeTuple()
        self.SetCurrent(self.context)
        glClearColor(1.0, 1.0, 1.0, 0.0)


    def onPaint(self, *args):
        if not self.shouldDraw:
            # Something's gone wrong; give up on drawing.
            return
        try:
            if not self.haveInitedGL:
                self.initGL()
                self.haveInitedGL = True

            self.SetCurrent(self.context)
            glViewport(0, 0, self.width, self.height)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(-.375, self.width - .375, -.375, self.height - .375, 1, -1)
            glMatrixMode(GL_MODELVIEW)
            
            if self.shouldRefresh:
                self.loadTile()
                self.tile.refresh()
                self.shouldRefresh = False
                
            glMatrixMode(GL_MODELVIEW)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glEnable(GL_TEXTURE_2D)
            # Fake viewbox; always draw everything.
            self.tile.render(((-self.width, -self.height), (self.width, self.height)))
            glDisable(GL_TEXTURE_2D)

            # Draw a polygon, if valid.
            if self.polygonPoints:
                glColor3fv(self.rectColor)
                glBegin(GL_LINE_STRIP)
                for x, y in self.polygonPoints + [self.rectVert2]:
                    glVertex2f(x, self.height - y)
                glEnd()
            # Draw a rectangle, if valid.
            elif self.rectColor is not None:
                glColor3fv(self.rectColor)
                glBegin(GL_LINE_LOOP)
                glVertex2f(self.rectVert1[0], self.height - self.rectVert1[1])
                glVertex2f(self.rectVert1[0], self.height - self.rectVert2[1])
                glVertex2f(self.rectVert2[0], self.height - self.rectVert2[1])
                glVertex2f(self.rectVert2[0], self.height - self.rectVert1[1])
                glEnd()
                
            glFlush()
            self.SwapBuffers()
        except Exception, e:
            # Something went wrong while drawing; give up on drawing so
            # we don't spam the logs with error messages.
            print "Failed while drawing: %s" % e
            self.shouldDraw = False
        

    ## Set us up to show a new pattern.
    def setDisplay(self, data):
        # Invert display vertically.
        self.curDisplay = data[::-1]
        self.shouldRefresh = True
        wx.CallAfter(self.Refresh)


    ## Load our display data onto our tile.
    def loadTile(self):
        self.tile = gui.mosaic.tile.Tile(self.curDisplay, (0, 0),
                (self.width, self.height), [0, 1], 0)


    ## Update the canvas size.
    def setSize(self, newSize):
        self.SetSize(newSize)
        self.width, self.height = newSize
        self.tile = None
        wx.CallAfter(self.Refresh)


    ## Map from screen coordinates to data coordinates.
    def remapPosition(self, pos):
        if self.width is None:
            # Haven't initialized GL yet; don't know the canvas size.
            return pos
        x = int(float(pos[0]) / self.width * self.curDisplay.shape[1])
        y = int(float(pos[1]) / self.height * self.curDisplay.shape[0])
        return x, y

