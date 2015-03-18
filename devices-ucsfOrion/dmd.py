import depot
import device
import events
import gui.camera.window
import gui.guiUtils
import gui.keyboard
import gui.mosaic.tile
import gui.toggleButton
import interfaces.imager
import interfaces.stageMover
import util.user

import ctypes
import numpy
from OpenGL.GL import *
import os
import time
import traceback
import wx
import wx.glcanvas

CLASS_NAME = 'DMDDevice'


## Width in pixels of the button bar.
BUTTON_WIDTH = 100

## Number of different grayscale values we allow (including black and white).
# Since the DMD device itself is black-and-white, these shades will be
# achieved by performing timewise dithering.
NUM_COLORS = 11

## Path to the file where DMD patterns are written to prior to them being
# loaded onto the DMD itself.
DMD_PATH = os.path.join('C:', os.path.sep, 'Users', 'Administrator', 'Documents',
    'Mosaic C++ stuff', 'DLL_console_Cockpit', 'x64', 'Release', 'bufData.bin')

## For debugging ease of access, a global copy of the most-recently-created
# window.
window = None



## This Device code just exists to create a UI for interacting with the
# Mosaic DMD.
class DMDDevice(device.Device):
    def makeUI(self, parent):
        button = gui.toggleButton.ToggleButton(parent = parent, label = "DMD",
                size = (120, 50))
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: DMDWindow())
        return button



## This window contains the widgets for interacting with the Mosaic DMD.
class DMDWindow(wx.Frame):
    def __init__(self):
        # Disable window resizing to preserve a 1:1 ratio of pixels to
        # DMD array data.
        wx.Frame.__init__(self, parent = None, title = "DMD pattern display",
                style = wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        global window
        window = self

        ## Panel containing the widgets in the DMD control.
        self.panel = None
        ## Height of the controls.
        self.controlsHeight = 0
        ## Canvas for displaying the DMD pattern.
        self.canvas = None
        ## Last known mouse click position.
        self.prevMousePos = None
        ## Boolean indicating if we are busy calibrating.
        self.amCalibrating = False
        ## Array of pixel values representing the currently-displayed
        # DMD pattern.
        self.data = None
        ## Maps Sites to array values for the DMD.
        self.siteToPattern = {}
        ## Maps strings to remembered patterns.
        self.nameToPattern = {}
        ## Ordered list of the keys to the above.
        self.nameOrder = []
        ## Current camera whose images we are listening for.
        self.camHandler = None
        ## Vertices of the rectangle we use for calibration.
        self.testVertices = ((200, 200), (400, 400))
        ## Tooltip text for our canvas for normal use.
        self.canvasTooltip = ("Left-click to draw rectangles in the " +
                "current color, right-click to draw black ones. " +
                "Hold shift to draw polygons.")
        ## Tooltip text for our canvas when calibrating.
        self.calibrateTooltip = "Please click on each of the four corners " + \
                "of the square."

        self.loadArray()
        
        self.panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Set up controls along the top of the main panel
        controlsPanel = wx.Panel(self.panel)
        controlsSizer = wx.GridSizer(3, 5, 0, 0)
        for label, action, helpText in [
                ('Write to DMD', lambda event: self.writeArray(self.data),
                 "Load the currently-drawn pattern onto the DMD."),
                ('Reload from DMD', lambda event: self.loadArray(),
                 "Load and display the pattern currently on the DMD."),
                ('Clear to white', lambda event: self.clear(NUM_COLORS - 1),
                 "Clear the entire field to white."),
                ('Clear to black', lambda event: self.clear(0),
                 "Clear the entire field to black."),
                ('Abort drawing', lambda event: self.stopDrawing(),
                 "Stop drawing a rectangle or polygon."),
                ('Record for site', lambda event: self.recordForSite(),
                 "Automatically load this pattern when we arrive at " +
                 "a specific site."),
                ('Calibrate', lambda event: self.calibrate(),
                 "Loads a test pattern and takes an image. After the image " +
                 "is acquired, click on the four corners of the test " +
                 "pattern to derive the transformation from the DMD to the " +
                 "camera."),
                ('Store pattern', lambda event: self.savePattern(),
                 "Remember this pattern for later re-use within the same " +
                 "microscope session."),
                ('Manage patterns', lambda event: self.managePatterns(),
                 "Bring up a dialog for interacting with stored patterns."),
                (None, None, None)]:
            if label is None:
                # Just add a spacer instead.
                controlsSizer.Add((1, 1))
                continue
            button = wx.Button(controlsPanel, -1, label,
                    size = (BUTTON_WIDTH, -1))
            button.SetToolTipString(helpText)
            button.Bind(wx.EVT_BUTTON, action)
            controlsSizer.Add(button, 0, wx.EXPAND)

        # Add a dropdown menu for loading a camera image.
        cameras = depot.getHandlersOfType(depot.CAMERA)
        camNames = [cam.name for cam in cameras]
        ## Dropdown menu for selecting a camera to load image data from.
        self.camSelector = wx.Choice(controlsPanel, -1, choices = camNames)
        self.camSelector.Bind(wx.EVT_CHOICE, self.onSelectCam)
        controlsSizer.Add(wx.StaticText(controlsPanel, -1, "Load image from camera: "))
        controlsSizer.Add(self.camSelector)

        ## Dropdown menu for setting the current color intensity.
        self.colorSelector = wx.Choice(controlsPanel, -1,
                choices = map(str, numpy.arange(0, 1.0001, 1 / float(NUM_COLORS - 1))))
        self.colorSelector.SetSelection(NUM_COLORS - 1)
        controlsSizer.Add(wx.StaticText(controlsPanel, -1, "Pixel intensity: "))
        controlsSizer.Add(self.colorSelector)

        controlsPanel.SetSizerAndFit(controlsSizer)
        sizer.Add(controlsPanel)

        self.controlsHeight = controlsPanel.GetClientSize()[1]
        
        self.canvas = DMDCanvas(self.panel, self.data)
        self.canvas.SetToolTipString(self.canvasTooltip)
        ## Propagate size events through to the canvas.
        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.canvas.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        sizer.Add(self.canvas, 1)
        self.panel.SetSizerAndFit(sizer)
        self.SetClientSize((800, 600 + self.controlsHeight))
        self.Show()

        gui.keyboard.setKeyboardHandlers(self)

        events.subscribe('arrive at site', self.onGoToSite)
        events.subscribe('load DMD pattern', self.setPattern)


    ## We've changed size; resize the canvas to suit.
    def onSize(self, event):
        width, height = self.GetClientSizeTuple()
        self.canvas.SetSize((width, height - self.controlsHeight))
        event.Skip()


    ## We've been closed; unsubscribe from events, if applicable.
    def onClose(self, event):
        if self.camHandler is not None:
            events.unsubscribe('new image %s' % self.camHandler.name,
                    self.onCameraImage)
        events.unsubscribe('arrive at site', self.onGoToSite)
        events.unsubscribe('load DMD pattern', self.setPattern)
        event.Skip()


    ## User selected a camera; load image data from it, if applicable.
    def onSelectCam(self, event = None):
        if self.camHandler is not None:
            # Unsubscribe from receiving the old camera's images.
            events.unsubscribe('new image %s' % self.camHandler.name,
                    self.onCameraImage)
        camName = self.camSelector.GetStringSelection()
        self.camHandler = depot.getHandlerWithName(camName)
        events.subscribe('new image %s' % self.camHandler.name,
                self.onCameraImage)
        # Load the current image, if possible.
        image = gui.camera.window.getImageForCamera(self.camHandler)
        if image is not None:
            self.onCameraImage(image)


    ## Received an image from our camera; display it on the canvas.
    def onCameraImage(self, image, timestamp = None):
        self.canvas.setCamData(image)


    ## User wants to calibrate the DMD (i.e. get the transformations to/from
    # camera/DMD coordinate spaces). We draw a test pattern and ask the
    # user to mark the vertices of the pattern on the camera view.
    def calibrate(self):
        if not self.camSelector.GetStringSelection():
            # No camera selected.
            gui.guiUtils.showHelpDialog(self,
                    "Please select a camera before attempting calibration.")
            return
        self.canvas.SetToolTipString(self.calibrateTooltip)
        self.amCalibrating = True
        self.canvas.resetTransform()
        self.data[:] = 0
        (v1x, v1y), (v2x, v2y) = self.testVertices
        self.data[v1x : v2x, v1y : v2y] = 1
        self.writeArray(self.data)
        # Actually display a blank pattern to make it easier to see the
        # camera display.
        self.data[:] = 0
        self.canvas.setDisplay(self.data)
        # Take an image and load it onto the canvas.
        interfaces.imager.takeImage()


    ## Remember the current pattern under a user-provided name.
    def savePattern(self, data = None, name = None):
        if data is None:
            data = numpy.array(self.data)
        if name is None:
            name = wx.GetTextFromUser("Name this pattern:")
            if not name:
                return
        if name in self.nameToPattern:
            # Name already in use.
            gui.guiUtils.showHelpDialog(self, "That name is already in use.")
            return
        self.nameToPattern[name] = numpy.array(self.data)
        self.nameOrder.append(name)


    ## Bring up a dialog that allows the user to manipulate patterns
    def managePatterns(self):
        ManagePatternsDialog(self, dict(self.nameToPattern),
                list(self.nameOrder),
                self.deletePattern, self.setNameOrder, self.setPattern,
                self.setNewSequence).Show()


    ## Delete the pattern with the given name.
    def deletePattern(self, name):
        del self.nameToPattern[name]
        del self.nameOrder[self.nameOrder.index(name)]


    ## Set a new name order.
    def setNameOrder(self, newOrder):
        self.nameOrder = newOrder


    ## Set a new pattern by name or by number, and load it onto the DMD.
    def setPattern(self, name = None, index = None):
        if name is not None:
            self.data[:] = self.nameToPattern[name]
        elif index is not None:
            self.data[:] = self.nameToPattern[self.nameOrder[index]]
        self.canvas.setDisplay(self.data)
        self.writeArray(self.data)


    ## Set an entirely new set of sequences.
    def setNewSequence(self, nameToPattern, nameOrder):
        self.nameOrder = nameOrder
        self.nameToPattern = nameToPattern


    ## A mouse event was posted to the canvas. Left/right clicking starts or
    # ends drawing rectangles; general mouse motion updates the vertices.
    def onMouse(self, event):
        curPos = self.canvas.screenToData(event.GetPosition())
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
            # Use the currently-selected color instead.
            value = self.colorSelector.GetSelection()
            rectColor = (0, 0, 255)
        if event.LeftDown() or event.RightDown():
            if event.ShiftDown() or self.amCalibrating:
                # Shift is held, or the user is calibrating the
                # view transform; draw a polygon. 
                self.canvas.polygonPoints.append(curPos)
                self.canvas.rectColor = rectColor
                if len(self.canvas.polygonPoints) == 4 and self.amCalibrating:
                    # Done marking rectangle points.
                    self.amCalibrating = False
                    self.canvas.calibrate(self.canvas.polygonPoints,
                            *(self.testVertices))
                    self.canvas.polygonPoints = []
                    self.canvas.rectColor = None
                    self.canvas.SetToolTipString(self.canvasTooltip)
            elif self.canvas.polygonPoints:
                # Draw a polygon, including the most recent point.
                self.canvas.polygonPoints.append(curPos)
                self.rasterizePolygon(self.canvas.polygonPoints, value)
                self.canvas.setDisplay(self.data)
                self.canvas.polygonPoints = []
                self.prevMousePos = None
                self.canvas.rectColor = None
            elif self.prevMousePos is not None:
                # Draw a rectangle from the previous position to the new one.
                self.rasterizeRect((minX, minY), (maxX, maxY), value)
                self.canvas.setDisplay(self.data)
                self.prevMousePos = None
                self.canvas.rectColor = None
            else:
                # Save the current mouse position for future rectangle drawing.
                self.prevMousePos = curPos
                self.canvas.rectVert1 = curPos
                self.canvas.rectColor = rectColor
        elif event.GetWheelRotation():
            # Debugging function: display info on the mouse position.
            print "Mouse click at",event.GetPosition(),"data coords",curPos
            self.canvas.cameraToData(curPos)
        self.canvas.Refresh()


    ## Given a rect in camera coordinates, fill in the appropriate pixels
    # in the data array.
    def rasterizeRect(self, p1, p2, value):
        # Our points are in camera coordinates, but with inverted Y. We need
        # to map them to data coordinates.
        fixedPoints = []
        for p in [p1, p2]:
            fixedPoints.append(self.canvas.cameraToData(p))
        p1, p2 = fixedPoints
        p1 = map(int, p1)
        p2 = map(int, p2)
        self.data[p1[1] : p2[1], p1[0] : p2[0]] = value


    ## Convert the provided list of points into a rasterized polygon.
    # Function adapted from http://en.wikipedia.org/wiki/Even-odd_rule
    # \param points List of polygon vertices in data coordinates.
    def rasterizePolygon(self, points, value):
        # Our points are in camera coordinates, but with inverted Y. We need
        # to map them to data coordinates.
        fixedPoints = []
        for p in points:
            fixedPoints.append(self.canvas.cameraToData(p))
        points = fixedPoints
        
        # Force a loop.
        points.append(points[0])
        minX = int(min(p[0] for p in points))
        maxX = int(max(p[0] for p in points))
        minY = int(min(p[1] for p in points))
        maxY = int(max(p[1] for p in points))
        for y in xrange(max(0, minY), min(self.data.shape[0], maxY + 1)):
            for x in xrange(max(0, minX), min(self.data.shape[1], maxX + 1)):
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
                    self.data[(y, x)] = value


    ## Write a new pattern to the DMD. We take this moment to implement
    # timewise dithering: 0 = off, (NUM_COLORS - 1) = 100% on,
    # everything else is a timewise dither. Thus, multiple buffers get
    # written.
    # \param specificIndex Debugging option to only output a specific single
    # buffer.
    def writeArray(self, data, specificIndex = None):
        assert(data.shape == (600, 800))
        indices = range(NUM_COLORS - 1)
        if specificIndex is not None:
            indices = [specificIndex]
        # Because we want even spacing of the on/off states for pixels that
        # are dithered in time, we'll use this summation buffer to track
        # when a pixel should be on vs. off. Each iteration, each pixel adds
        # to this buffer a value based on that pixel's frequency; when the
        # buffer exceeds 1, we write an "on" state for that pixel and subtract
        # 1 from the buffer.
        summationBuffer = numpy.zeros(data.shape, dtype = numpy.float32)
        # This is what we'll add to summationBuffer in each iteration.
        addendBuffer = numpy.zeros(data.shape, dtype = numpy.float32)
        addendBuffer[:] = data / float(NUM_COLORS - 1)
        
        handle = open(DMD_PATH, 'wb')
        for i in indices:
            # Note: when looking at the pattern in the camera, 1 = "dark",
            # 0 = "bright". Hence we start with a dark default and fill in
            # the bright pixels.
            temp = numpy.ones((data.shape), dtype = numpy.uint8)
            summationBuffer += addendBuffer
            onIndices = numpy.where(summationBuffer >= 1)
            temp[onIndices] = 0
            summationBuffer[onIndices] -= 1
            # Collapse to a linear array.
            temp.shape = numpy.product(temp.shape)
            handle.write(numpy.packbits(temp))
        handle.close()


    ## Write a single value to the entire array.
    def clear(self, newVal):
        self.data[:] = newVal
        self.canvas.setDisplay(self.data)


    ## Abort drawing a polygon or rectangle.
    def stopDrawing(self):
        self.prevMousePos = None
        self.canvas.polygonPoints = []
        self.canvas.rectVert1 = None
        self.canvas.rectColor = None


    ## Load the current pattern from the DMD. Except that we can't directly
    # access the DMD pattern; instead we load the patterns we last wrote
    # to the intermediary file.
    # \todo For now, only "restoring" the first pattern in that file, not
    # all of them (thus timewise dithering is lost).
    def loadArray(self):
        try:
            handle = open(DMD_PATH, 'rb')
            # Divide by 8 because the buffers are 1 bit per pixel but the
            # datatype is 8 bits per pixel, so we're packing 8 pixels into
            # each element.
            data = numpy.fromfile(handle, dtype = numpy.uint8,
                    count = 800 * 600 / 8)
            # Now unpack those elements.
            data = numpy.unpackbits(data)
            print "Unpacked pixels have shape",data.shape
            data.shape = (600, 800)
            # Reverse 0 and 1.
            data[numpy.where(data == 1)] = 2
            data[numpy.where(data == 0)] = 1
            data[numpy.where(data == 2)] = 0
            # Remap (0, 1) to (0, MAX_SHADES - 1)
            data *= (NUM_COLORS - 1)
        except Exception, e:
            print "There was an error loading the previous buffer:",e
            # Just use a blank canvas.
            data = numpy.zeros((600, 800), dtype = numpy.uint8)
        self.data = data
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

        ## Scale factor to apply when remapping the DMD display onto
        # camera coordinates.
        self.scaleX = self.scaleY = .55
        ## Offset to apply when remapping the DMD display onto camera
        # coordinates.
        self.offset = [-5, -1.5]
        ## Rotation, in radians, to apply when remapping the DMD display
        # onto camera coordinates.
        self.rotation = 0

        ## Array of pixel values representing the current camera image.
        self.camData = None
        ## gui.mosaic.tile.Tile instance for drawing the camera image.
        self.camTile = None
        ## Whether or not we need to reset the above Tile.
        self.shouldResetCamTile = False

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

            if self.shouldResetCamTile:
                # Replace the camera tile with a new one.
                if self.camTile is not None:
                    self.camTile.wipe()
                self.camTile = gui.mosaic.tile.Tile(self.camData,
                        (0, 0), self.camData.shape,
                        (self.camData.min(), self.camData.max()), 0)
            
            if self.shouldRefresh:
                self.loadTile()
                self.tile.refresh()
                if self.camTile is not None:
                    self.camTile.refresh()
                self.shouldRefresh = False
                
            glMatrixMode(GL_MODELVIEW)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            # Draw a white rectangle over everything, for blending.
            glBegin(GL_QUADS)                
            glColor3i(1, 1, 1)
            glVertex2i(0, 0)
            glVertex2i(self.width, 0)
            glVertex2i(self.width, self.height)
            glVertex2i(0, self.height)

            if self.camTile is not None:
                # Draw a black rectangle over the camera view area for
                # blending.
                glColor3i(0, 0, 0)
                glVertex2i(0, 0)
                glVertex2i(self.camData.shape[0], 0)
                glVertex2iv(self.camData.shape)
                glVertex2i(0, self.camData.shape[1])
                
            glEnd()

            # Draw our pattern and the camera view, if applicable.
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_ONE, GL_ONE)
            # Fake viewbox; always draw everything.
            viewbox = ((-self.width, -self.height), (self.width, self.height))
            if self.camTile is not None:
                self.camTile.render(viewbox)

            # Apply the DMD -> camera transformation, and draw our data plus
            # a green rectangle outlining the boundaries of that data.
            glPushMatrix()
            glScaled(self.scaleX, self.scaleY, 1)
            glRotated(-self.rotation * 180 / numpy.pi, 0, 0, 1)
            glTranslated(self.offset[0], self.offset[1], 0)
            
            self.tile.render(viewbox)
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)

            # NOTE: assuming self.width and self.height match the original
            # data boundaries!
            glColor3f(0, 1, 0)
            glBegin(GL_LINE_LOOP)
            glVertex2f(0, 0)
            glVertex2f(0, self.height)
            glVertex2f(self.width, self.height)
            glVertex2f(self.width, 0)
            glEnd()
            
            glPopMatrix()

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
            traceback.print_exc()
        

    ## Set us up to show a new pattern.
    def setDisplay(self, data):
        # Invert display vertically, and rescale values to run from
        # 0 to .5 for better transparency display.
        self.curDisplay = data[::-1].astype(numpy.float32)
        self.curDisplay /= float(NUM_COLORS)
        self.shouldRefresh = True
        wx.CallAfter(self.Refresh)


    ## Receive a new camera image.
    def setCamData(self, camData):
        self.camData = camData
        self.shouldResetCamTile = True
        self.Refresh()


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


    ## Derive the transformation from DMD coordinates to camera coordinates.
    # \param clickedPoints Points that the user clicked on.
    # \param v1 First vertex of the test rectangle, assumed to be
    #           the smaller two coordinates of a rectangle. In data coords.
    # \param v2 Second vertex of the test rectangle, assumed to be
    #           the larger two coordinates of a rectangle. In data coords.
    def calibrate(self, clickedPoints, v1, v2):
        # Fix the Y coordinates of the inputs.
        clickedPoints = [(c[0], self.height - c[1]) for c in clickedPoints]
        # Remap the test pattern vertices to screen coords, to match the
        # above.
        v1 = self.dataToScreen(v1)
        v2 = self.dataToScreen(v2)
        
        # Order the clicked points so that the lower-left (smallest-valued)
        # vertex is first and the rest follow in clockwise order.
        temp = list(clickedPoints)
        temp.sort(key = lambda (a, b): (a ** 2) + (b ** 2))
        first = temp[0]
        del temp[0]
        # Second vertex should be above first vertex, so prefer minimal X
        # variation.
        temp.sort(key = lambda (a, b): abs(a - first[0]))
        second = temp[0]
        del temp[0]
        # Third vertex should be right of second vertex, so prefer minimal
        # Y variation.
        temp.sort(key = lambda (a, b): abs(b - second[1]))
        third, fourth = temp

        orderedPoints = [first, second, third, fourth]

        # Derive the scale based on the different sizes of the drawn vs.
        # projected rectangles.
        testWidth = v2[0] - v1[0]
        trueWidth = (fourth[0] - first[0] + third[0] - second[0]) / 2.0
        self.scaleX = trueWidth / testWidth
        testHeight = v2[1] - v1[1]
        trueHeight = (second[1] - first[1] + third[1] - fourth[1]) / 2.0
        self.scaleY = trueHeight / testHeight

        # Angle is disabled pending figuring out how to keep it from
        # getting 90 degrees off sometimes. It should be nearly zero anyway.
##        # Derive the rotation angle based on how far off of a right angle
##        # each corner is assuming the "incoming" vector is straight.
##
##        vectors = []
##        for i in xrange(4):
##            a = orderedPoints[i]
##            b = orderedPoints[(i + 1) % 4]
##            vectors.append((b[0] - a[0], b[1] - a[1]))
##        totalDiff = 0
##        for i, vec in enumerate(vectors):
##            # Remember arctan2 wants the Y value first, hence the flip.
##            angle = numpy.arctan2(*(vec[::-1]))
##            target = (numpy.pi / 2) - (i * numpy.pi / 2)
##            diff = (angle - target) % numpy.pi
##            totalDiff += diff
##        self.rotation = totalDiff / 4
##
##        print "Angle is",self.rotation

        # Transform our pattern-space coordinates now, so we can derive the
        # translation.
        self.offset = [0, 0]
        v1 = self.transformVertex(*v1)
        v2 = self.transformVertex(*v2)

        # Derive translation based on the average difference between the
        # clicked points and the modified pattern-space coordinates.
        dx = dy = 0
        basePoints = [v1, (v1[0], v2[1]), v2, (v2[0], v1[1])]
        for i, (clicked, base) in enumerate(zip(orderedPoints, basePoints)):
            dx += clicked[0] - base[0]
            dy += clicked[1] - base[1]

        self.offset[0] = dx / 4.0
        self.offset[1] = dy / 4.0

        print "Calibration transforms are",self.offset,self.scaleX,self.scaleY

        self.Refresh()


    ## Given input vertices in screen coordinates, remap to camera coordinates.
    def transformVertex(self, x, y):
        radius = numpy.sqrt((x ** 2 + y ** 2))
        angle = numpy.arctan2(y, x)
        angle += self.rotation
        x = radius * numpy.cos(angle)
        y = radius * numpy.sin(angle)

        return (x * self.scaleX + self.offset[0], y * self.scaleY + self.offset[1])


    ## Reset our transformation parameters.
    def resetTransform(self):
        self.scaleX = self.scaleY = 1
        self.rotation = 0
        self.offset = [0, 0]


    ## Map from screen coordinates to data coordinates.
    def screenToData(self, pos):
        if self.width is None:
            # Haven't initialized GL yet; don't know the canvas size.
            return pos
        x = int(float(pos[0]) / self.width * self.curDisplay.shape[1])
        y = int(float(pos[1]) / self.height * self.curDisplay.shape[0])
        return x, y


    ## Map from data coordinates to screen coordinates.
    def dataToScreen(self, pos):
        if self.width is None:
            # Haven't initialized GL yet; don't know the canvas size.
            return pos
        x = int(float(pos[0]) * self.width / self.curDisplay.shape[1])
        y = int(float(pos[1]) * self.height / self.curDisplay.shape[0])
        return x, y


    ## Map from camera coordinates to data coordinates.
    def cameraToData(self, pos):
        # First subtract off our transformed upper-left corner.
        upperLeft = list(self.transformVertex(0, self.height))
        upperLeft[1] = self.height - upperLeft[1]
        x = pos[0] - upperLeft[0]
        y = pos[1] - upperLeft[1]
        x = (x / self.scaleX) - self.offset[0]
        y = (y / self.scaleY) - self.offset[1]
        return (x, y)



## Dialog for interacting with stored patterns.
class ManagePatternsDialog(wx.Dialog):
    ## \param nameToPattern Maps names to data arrays of DMD patterns.
    # \param nameOrder Ordered list of pattern names.
    # \param delFunc Function to call when deleting a pattern.
    # \param setOrderFunc Function to call when reordering the pattern list.
    # \param setPatternFunc Function to call when setting a new pattern.
    # \param setNewSequenceFunc Function to call when loading an entirely
    #        new sequence.
    def __init__(self, parent, nameToPattern, nameOrder, delFunc,
            setOrderFunc, setPatternFunc, setNewSequenceFunc):
        wx.Dialog.__init__(self, parent, -1, "Manage stored patterns")

        self.nameToPattern = nameToPattern
        self.nameOrder = nameOrder
        self.delFunc = delFunc
        self.setOrderFunc = setOrderFunc
        self.setPatternFunc = setPatternFunc
        self.setNewSequenceFunc = setNewSequenceFunc
        
        self.panel = None

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.genUI()


    ## [Re]create the UI based on our current name order.
    def genUI(self):
        if self.panel is not None:
            self.sizer.Clear()
            self.panel.Destroy()
        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        # Have a sub-panel for each pattern, associated with that panel's
        # name.
        self.nameToPatternPanel = {}
        for name in self.nameOrder:
            subPanel = wx.Panel(self.panel)
            subSizer = wx.BoxSizer(wx.HORIZONTAL)
            subSizer.Add(wx.StaticText(subPanel, -1, "%s:" % name),
                    0, wx.TOP | wx.RIGHT, 3)
            for name, action, tooltip in [
                    ("Up", lambda event, name = name: self.move(name, -1),
                     "Move this pattern earlier in the sequence."),
                    ("Down", lambda event, name = name: self.move(name, 1),
                     "Move this pattern later in the sequence."),
                    ("Delete", lambda event, name = name: self.delete(name),
                     "Remove this pattern from the sequence."),
                    ("Load", lambda event, name = name: self.load(name),
                     "Make this the current pattern.")]:
                button = wx.Button(subPanel, -1, name)
                button.Bind(wx.EVT_BUTTON, action)
                button.SetToolTipString(tooltip)
                subSizer.Add(button)
            subPanel.SetSizerAndFit(subSizer)
            self.sizer.Add(subPanel, 0, wx.ALL, 1)

        # Final set of sizers for saving/loading to/from file.
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        # Spacer.
        rowSizer.Add((1, -1), 1, wx.EXPAND)

        for name, action, tooltip in [
                ("Save sequence", lambda event: self.saveSequence(),
                 "Save this sequence of patterns to a file for later re-use."),
                ("Load sequence", lambda event: self.loadSequence(),
                 "Load a previously-saved sequence of patterns.")]:
            button = wx.Button(self.panel, -1, name)
            button.Bind(wx.EVT_BUTTON, action)
            button.SetToolTipString(tooltip)
            rowSizer.Add(button, 0, wx.ALL, 1)

        self.sizer.Add(rowSizer)

        self.panel.SetSizerAndFit(self.sizer)


    def move(self, name, offset):
        curIndex = self.nameOrder.index(name)
        targetIndex = curIndex + offset
        if targetIndex == len(self.nameOrder):
            # Sending off the bottom of the array; move it to the top.
            targetIndex = 0
        elif targetIndex == -1:
            # Sending off the top of the array; move it to the end.
            targetIndex = len(self.nameOrder)
        newList = list(self.nameOrder)
        del newList[curIndex]
        newList.insert(targetIndex, name)
        self.nameOrder = newList
        self.setOrderFunc(newList)
        self.genUI()


    ## Remove the offending pattern, after confirmation.
    def delete(self, name):
        if not gui.guiUtils.getUserPermission(
                "Are you sure you want to forget this pattern?"):
            # User cancelled.
            return
        del self.nameOrder[self.nameOrder.index(name)]
        self.delFunc(name)
        self.genUI()


    ## Set the named pattern as the current visible pattern.
    def load(self, name):
        self.setPatternFunc(name)
        

    ## Save the current sequence to a file.
    def saveSequence(self):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE,
                message = "Please select a filename to save to",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        path = dialog.GetPath()
        handle = open(path, 'wb')
        # We want to preserve the pattern ordering, so prepend the
        # index of each pattern name to the pattern's name.
        newMap = {}
        for name, pattern in self.nameToPattern.iteritems():
            index = self.nameOrder.index(name)
            # Anyone using more than 9999999999 patterns is a madman.
            newMap["%010d:%s" % (index, name)] = pattern
        numpy.savez_compressed(handle, **newMap)
        handle.close()


    ## Load a previously-saved sequence from a file.
    def loadSequence(self):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN,
                message = "Please select a sequence file to load",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        path = dialog.GetPath()
        nameToPattern = numpy.load(path)

        # Generate a new name order and nameToPattern mapping from the names
        # provided.
        self.nameToPattern = {}
        self.nameOrder = []
        # Sorting names puts them in the proper order because the index
        # comes first.
        for name in sorted(nameToPattern.keys()):
            pattern = nameToPattern[name]
            # The index is the first component; the rest comprise the name
            # proper.
            nameComponents = name.split(':')
            name = ':'.join(nameComponents[1:])
            self.nameOrder.append(name)
            self.nameToPattern[name] = pattern
        self.setNewSequenceFunc(self.nameToPattern, self.nameOrder)
        self.genUI()
