import events
import gui.guiUtils
import image
import util.threads

import FTGL
import numpy
from OpenGL.GL import *
import os
import Queue
import threading
import traceback
import wx
import wx.glcanvas

from cockpit import COCKPIT_PATH

## @package gui.imageViewer.viewCanvas
# This module provides a canvas for displaying camera images.

## Maximum number of bins for the histogram
MAX_BINS = 128
## Display height of the histogram, in pixels
HISTOGRAM_HEIGHT = 40

## Drag modes
(DRAG_NONE, DRAG_CANVAS, DRAG_BLACKPOINT, DRAG_WHITEPOINT) = range(4)

## This class handles displaying multi-channel 2D images.
# Most of the actual drawing logic is handled in the image.Image class.
# It can handle arbitrarily-sized images, by cutting them up into parcels
# and tiling them together. 
class ViewCanvas(wx.glcanvas.GLCanvas):
    ## Instantiate.
    def __init__(self, parent, tileSize, mouseHandler = None, *args, **kwargs):
        wx.glcanvas.GLCanvas.__init__(self, parent, *args, **kwargs)

        ## Parent, so we can adjust its size when we receive an image.
        self.parent = parent

        ## We set this to false if there's an error, to prevent OpenGL
        # error spew.
        self.shouldDraw = True

        ## Should we show a crosshair (used for alignment)?
        self.showCrosshair = False

        ## Edge length of one tile.
        self.tileSize = tileSize

        ## Shape of our tile grid. Changes when setImage is called.
        self.tileShape = None

        ## 2D array of Image instances. Created when setImage is called
        # with a new image shape.
        self.tiles = []

        ## Optional additional mouse handler function.
        self.mouseHandler = mouseHandler

        ## Queue of incoming images that we need to either display or discard.
        self.imageQueue = Queue.Queue()
        ## Current image we're working with.
        self.imageData = None
        ## Event that signals that we've finished drawing the current image.
        self.drawEvent = threading.Event()
        # This spawns a new thread.
        self.processImages()
        ## Min/max values in our image
        self.imageMin = self.imageMax = 0
        ## Percentile scaling of min/max based on our histogram.
        self.blackPoint, self.whitePoint = 0.0, 1.0

        ## Size of image we've received, which we use for determining
        # scale.
        self.imageShape = None

        ## Whether or not we need to call our images' refresh() methods
        # next time onPaint runs.
        self.shouldRefresh = True

        ## Overall scaling factor, separate from the above.
        self.zoom = 1.0

        ## Current mouse position
        self.curMouseX = self.curMouseY = None

        ## Mouse position as of most recent frame, when dragging.
        self.mouseDragX = self.mouseDragY = None

        ## Pan translation factor
        self.panX = 0
        self.panY = 0

        ## What kind of dragging we're doing.
        self.dragMode = DRAG_NONE

        ## Whether or not we've done some one-time initialization work.
        self.haveInitedGL = False

        ## WX context that we set when we need to do GL operations.
        self.context = wx.glcanvas.GLContext(self)

        ## Font for text rendering
        self.font = FTGL.TextureFont(
                os.path.join(COCKPIT_PATH, 'resources',
                             'fonts', 'GeosansLight.ttf'))
        self.font.FaceSize(18)

        self.Bind(wx.EVT_PAINT, self.onPaint)
        # Do nothing, to prevent flickering
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: 0)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)

        
    def InitGL(self):
        self.w, self.h = self.GetClientSize()
        self.SetCurrent(self.context)
        glClearColor(0.3, 0.3, 0.3, 0.0)   ## background color

        self.haveInitedGL = True


    ## Stop displaying anything. Optionally destroy the canvas at the end.
    @util.threads.callInMainThread
    def clear(self, shouldDestroy = False):
        # Clear out the queue of images.
        while True:
            try:
                self.imageQueue.get_nowait()
            except Queue.Empty:
                break
        self.imageData = None
        self.imageShape = None
        self.imageMin = None
        self.imageMax = None
        if self.tileShape is not None:
            for i in xrange(self.tileShape[0]):
                for j in xrange(self.tileShape[1]):
                    self.tiles[i][j].wipe()
        self.tiles = []
        self.tileShape = None
        if shouldDestroy:
            self.shouldDraw = False
            self.Destroy()
        else:
            self.Refresh()


    ## Receive a new image. This will trigger processImages(), below, to
    # actually display the image.
    def setImage(self, newImage):
        self.imageQueue.put_nowait(newImage)


    ## Consume images out of self.imageQueue and either display them or
    # discard them. Because images can arrive very rapidly at times, we
    # want to ensure that we don't jam up -- if several images arrive while
    # we process one image, then the extras get discarded.
    @util.threads.callInNewThread
    def processImages(self):
        while self.shouldDraw:
            # Grab all images out of the queue; we'll use the most recent one.
            newImage = self.imageQueue.get()
            while not self.imageQueue.empty():
                newImage = self.imageQueue.get_nowait()
            # We want to autoscale to the image if it's our first one.
            isFirstImage = self.imageData is None
            self.imageData = newImage
            # When the image shape changes, we reset back to filling the
            # display with the image.
            shouldResetView = self.imageShape != newImage.shape
            self.imageShape = newImage.shape
            
            self.imageMin = newImage.min()
            self.imageMax = newImage.max()
            self.recalculateHistogram(newImage)
            self.setTiles(newImage)
            if shouldResetView:
                self.resetView()
            if isFirstImage:
                wx.CallAfter(self.resetPixelScale)
            # Wait for the image to be drawn before we do anything more.
            self.drawEvent.wait()
            self.drawEvent.clear()


    ## Update our tiles, if necessary, because a new image has arrived.
    @util.threads.callInMainThread
    def setTiles(self, imageData):
        if not self.shouldDraw:
            return
        try:
            self.SetCurrent(self.context)
            # Whether or not self.tiles is currently valid.
            haveSetTiles = True
            # Calculate the tile layout we'll need, and see if it matches
            # the current layout. If it doesn't, then we need to create
            # a new set of tiles.
            width = int(numpy.ceil(float(imageData.shape[0]) / self.tileSize))
            height = int(numpy.ceil(float(imageData.shape[1]) / self.tileSize))
            if self.tileShape != (width, height):
                if self.tileShape is not None:
                    # Destroy old tiles to free up texture memory
                    for i in xrange(self.tileShape[0]):
                        for j in xrange(self.tileShape[1]):
                            self.tiles[i][j].wipe()
                self.tiles = []
                self.tileShape = (width, height)
                haveSetTiles = False
                
            for i in xrange(self.tileShape[0]):
                if not haveSetTiles:
                    self.tiles.append([])
                xMin = i * self.tileSize
                xMax = min((i + 1) * self.tileSize, self.imageShape[0])
                for j in xrange(self.tileShape[1]):
                    yMin = j * self.tileSize
                    yMax = min((j + 1) * self.tileSize, self.imageShape[1])
                    subData = imageData[xMin : xMax, yMin : yMax]
                    if not haveSetTiles:
                        self.tiles[i].append(image.Image(subData))
                    else:
                        self.tiles[i][j].updateImage(subData)

            if not haveSetTiles:
                self.changeHistScale(False)
        except Exception, e:
            print "Failed to set new image:",e
            import traceback
            traceback.print_exc()

        self.Refresh()


    ## Recalculate our histogram of pixel brightnesses.
    # There's a problem with our approach in that there may be "spikes"
    # in the histogram (buckets with 2x the size of their neighbors); this
    # is caused by some buckets claiming more ints than other buckets.
    # We may want to investigate this custom histogram code sometime:
    # https://github.com/kif/pyFAI/blob/master/src/histogram.pyx
    # It is claimed to be ~5x faster than Numpy's implementation.
    def recalculateHistogram(self, imageData):
        # Need a 1D array of integers for numpy.bincount
        temp = imageData.reshape(numpy.product(imageData.shape)).astype(numpy.int32)
        dataRange = temp.max() - temp.min()
        numBins = min(dataRange, MAX_BINS)
        self.binSizes = numpy.bincount(
                (temp - temp.min()) * numBins / dataRange
        )


    ## Reset our blackpoint/whitepoint based on the image data.
    def resetPixelScale(self):
        self.blackPoint = 0.0
        self.whitePoint = 1.0
        self.changeHistScale()


    ## Propagate changes to the histogram scaling to our tiles.
    def changeHistScale(self, shouldRefresh = True):
        newMin = self.blackPoint * (self.imageMax - self.imageMin) + self.imageMin
        newMax = self.whitePoint * (self.imageMax - self.imageMin) + self.imageMin
        if newMin is None or newMax is None:
            # No image; can't do anything.
            return
        for i in xrange(self.tileShape[0]):
            for j in xrange(self.tileShape[1]):
                self.tiles[i][j].setMinMax(newMin, newMax)
        self.shouldRefresh = True

        if shouldRefresh:
            self.Refresh(False)


    ## Return the blackpoint and whitepoint (i.e. the pixel values which
    # are displayed as black and white, respectively).
    def getScaling(self):
        if self.imageData is None or len(self.tiles) == 0:
            # No image to operate on yet.
            return (None, None)
        return (self.tiles[0][0].imageMin, self.tiles[0][0].imageMax)


    ## As above, but the values used to calculate them instead of the
    # absolute pixel values (e.g. (.1, .9) instead of (100, 400).
    def getRelativeScaling(self):
        return (self.blackPoint, self.whitePoint)

        
    def onPaint(self, event):
        if not self.shouldDraw:
            return
        try:
            dc = wx.PaintDC(self)
        except:
            return

        if not self.haveInitedGL:
            self.InitGL()

        try:
            self.SetCurrent(self.context)

            glViewport(0, 0, self.w, self.h)
            glMatrixMode (GL_PROJECTION)
            glLoadIdentity ()
            glOrtho (0, self.w, 0, self.h, 1., -1.)
            glMatrixMode (GL_MODELVIEW)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            if self.tiles:
                glPushMatrix()
                glLoadIdentity()
                glTranslatef(0, HISTOGRAM_HEIGHT, 0)

                if self.shouldRefresh:
                    for i in xrange(self.tileShape[0]):
                        for j in xrange(self.tileShape[1]):
                            self.tiles[i][j].refresh()
                self.shouldRefresh = False

                # Apply zoom
                glTranslatef(self.imageShape[1] / 2.0, self.imageShape[0] / 2.0, 0)
                glScalef(self.zoom, self.zoom, 1)
                glTranslatef(-self.imageShape[1] / 2.0, -self.imageShape[0] / 2.0, 0)

                # Apply pan
                glTranslatef(self.panX, self.panY, 0)

                glEnable(GL_TEXTURE_2D)

                # Draw the actual tiles.
                for i in xrange(self.tileShape[0]):
                    for j in xrange(self.tileShape[1]):
                        glPushMatrix()
                        glTranslatef(j * self.tileSize, i * self.tileSize, 0)
                        self.tiles[i][j].render()
                        glPopMatrix()

                glDisable(GL_TEXTURE_2D)
                glPopMatrix()

                self.drawHistogram()

                if self.showCrosshair:
                    self.drawCrosshair()

            glFlush()
            self.SwapBuffers()
            self.drawEvent.set()
        except Exception, e:
            print "Error drawing view canvas:",e
            traceback.print_stack()
            self.shouldDraw = False


    def drawCrosshair(self):
        glColor3f(0, 255, 255)
        glBegin(GL_LINES)
        glVertex2f(0, HISTOGRAM_HEIGHT + 0.5 * (self.h - HISTOGRAM_HEIGHT) )
        glVertex2f(self.w, HISTOGRAM_HEIGHT + 0.5 * (self.h - HISTOGRAM_HEIGHT) )
        glVertex2f(0.5 * self.w, HISTOGRAM_HEIGHT)
        glVertex2f(0.5 * self.w, self.h)
        glEnd()


    ## Draw the histogram of our data. 
    def drawHistogram(self):
        # White box over all
        glColor3f(255, 255, 255)
        glBegin(GL_QUADS)
        glVertex2f(0, 0)
        glVertex2f(self.w, 0)
        glVertex2f(self.w, HISTOGRAM_HEIGHT)
        glVertex2f(0, HISTOGRAM_HEIGHT)
        glEnd()

        # The actual histogram
        glBegin(GL_QUADS)
        glColor3f(0, 0, 0)
        binWidth = self.w / float(len(self.binSizes))
        maxVal = max(self.binSizes)
        for i, size in enumerate(self.binSizes):
            # Only draw if there's something there; otherwise we get the
            # occasional 1-pixel line.
            if size:
                xOff = i * binWidth
                # Subtract some pixels off the histogram height to leave room
                # for the text.
                height = size / float(maxVal) * (HISTOGRAM_HEIGHT - 15)
                glVertex2f(xOff, 0)
                glVertex2f(xOff + binWidth, 0)
                glVertex2f(xOff + binWidth, height)
                glVertex2f(xOff, height)
        glEnd()

        # Draw marks for the black and white points
        glColor3f(255, 0, 0)

        # The horizontal position of the marks are based on our
        # black and white points, and are positioned independent
        # of the current image data.
        for val, sign in [(self.blackPoint, 1), (self.whitePoint, -1)]:
            # Offset by 1 pixel to ensure we stay in-bounds even with min/max values
            xOff = val * self.w + sign
            glBegin(GL_LINE_STRIP)
            glVertex2f(xOff + sign * 15, 2)
            glVertex2f(xOff, 2)
            glVertex2f(xOff, HISTOGRAM_HEIGHT - 2)
            glVertex2f(xOff + sign * 15, HISTOGRAM_HEIGHT - 2)
            glEnd()

        # Draw explanatory text
        glColor3f(0, 0, 255)
        glPushMatrix()
        glTranslatef(25, 25, 0)
        # Left-align the data min by padding with spaces.
        minVal = str(self.imageMin)
        minVal += ' ' * (10 - len(minVal))
        self.font.Render('%d [%s %10d] %d' %
                (self.tiles[0][0].imageMin, self.imageMin,
                 self.imageMax, self.tiles[0][0].imageMax))
        glPopMatrix()


    ## Update the size of the canvas by scaling it.
    def setSize(self, size):
        if self.imageData is not None:
            self.w, self.h = size
        self.Refresh(0)


    def onMouse(self, event):
        if self.mouseHandler is not None:
            self.mouseHandler(event)
        self.curMouseX, self.curMouseY = event.GetPosition()
        self.updateMouseInfo(self.curMouseX, self.curMouseY)
        rotation = event.GetWheelRotation()
        if rotation:
            # Zoom the canvas
            self.modZoom(rotation / 1000.0)

        if event.LeftDown():
            # Started dragging
            self.mouseDragX, self.mouseDragY = self.curMouseX, self.curMouseY
            blackPointX = self.blackPoint * self.w
            whitePointX = self.whitePoint * self.w
            # Set drag mode based on current window position
            if self.h - self.curMouseY >= HISTOGRAM_HEIGHT * 2:
                self.dragMode = DRAG_CANVAS
            elif abs(self.curMouseX - blackPointX) < abs(self.curMouseX - whitePointX):
                self.dragMode = DRAG_BLACKPOINT
            else:
                self.dragMode = DRAG_WHITEPOINT
        elif event.LeftIsDown():
            # Drag mouse. Different behaviors depending on drag mode.
            if self.dragMode == DRAG_CANVAS:
                # Pan view about.
                # Window coordinates are upside-down compared to what the
                # user expects...
                self.modPan(self.curMouseX - self.mouseDragX,
                            self.mouseDragY - self.curMouseY)
            elif self.dragMode == DRAG_BLACKPOINT:
                # Move blackpoint.
                self.blackPoint += float(self.curMouseX - self.mouseDragX) / self.w
            elif self.dragMode == DRAG_WHITEPOINT:
                # Move whitepoint.
                self.whitePoint += float(self.curMouseX - self.mouseDragX) / self.w
            if self.dragMode in [DRAG_BLACKPOINT, DRAG_WHITEPOINT]:
                self.changeHistScale()
                
            self.mouseDragX = self.curMouseX
            self.mouseDragY = self.curMouseY
        elif event.RightDown():
            # Show a menu.
            menu = wx.Menu()
            for label, action in self.getMenuActions():
                id = wx.NewId()
                menu.Append(id, label)
                wx.EVT_MENU(self, id, lambda event, action = action: action())
            gui.guiUtils.placeMenuAtMouse(self, menu)

        # In case current mouse position has changed enough to require
        # redrawing the histogram. A bit wasteful of resources, this.
        wx.CallAfter(self.Refresh)


    ## Generate a list of (label, action) tuples to use for generating menus.
    def getMenuActions(self):
        return [('Reset view', self.resetView),
                ('Fill viewer', lambda: self.resetView(True)),
                ('Set histogram parameters', self.onSetHistogram),
                ('Toggle alignment crosshair', self.toggleCrosshair)]


    ## Let the user specify the blackpoint and whitepoint for image scaling.
    def onSetHistogram(self, event = None):
        values = gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                parent = self, title = "Set histogram scale parameters",
                prompts = ["Blackpoint", "Whitepoint"],
                defaultValues = [self.tiles[0][0].imageMin, self.tiles[0][0].imageMax])
        values = map(float, values)
        # Convert from pixel intensity values to [0, 1] scale values.
        divisor = float(self.imageMax - self.imageMin)
        self.blackPoint = (values[0] - self.imageMin) / divisor
        self.whitePoint = (values[1] - self.imageMin) / divisor
        self.changeHistScale(shouldRefresh = True)


    def toggleCrosshair(self, event=None):
        self.showCrosshair = not(self.showCrosshair)


    ## Display information on the pixel under the mouse at the given
    # position.
    def updateMouseInfo(self, x, y):
        if self.imageData is None or self.imageShape is None:
            # Not ready to get mouse info yet.
            return
        # First we have to convert from screen coordinates to texture
        # coordinates.
        coords = numpy.array([y, x])
        # Get from overall screen coords to image display screen coords.
        coords[0] = self.GetClientSize()[1] - coords[0] - HISTOGRAM_HEIGHT
        # Apply zoom
        shape = numpy.array(self.imageShape)
        coords = coords - ( shape / 2.0)
        coords /= self.zoom
        coords = coords + (shape / 2.0)
        # Apply pan
        coords -= [self.panY, self.panX]
        if numpy.all(coords < shape) and numpy.all(coords >= 0):
            value = self.imageData[int(coords[0]),int(coords[1])]
            events.publish("image pixel info", coords[::-1], value)
        

    ## Modify our overall zoom by the provided factor.
    def modZoom(self, factor):
        self.zoom += factor
        self.Refresh(0)


    ## Modify our panning amount by the provided factor.
    def modPan(self, dx, dy):
        self.panX += dx
        self.panY += dy
        self.Refresh(0)


    ## Reset our view mods.
    # \param shouldFillView If True, then scale the image so that the entire
    #        view area is filled, even if that results in offscreen pixels
    #        (because the image aspect ratio is not the viewer aspect ratio).
    #        If False, scale the image so it all fits into the viewer, even if
    #        this results in parts of the viewer having no image data.
    def resetView(self, shouldFillView = False):
        if self.imageShape is None:
            # No image to work with.
            return
        clientSize = list(self.GetClientSize())
        clientSize[1] -= HISTOGRAM_HEIGHT
        zoom = float(clientSize[0]) / self.imageShape[0]
        operator = (min, max)[shouldFillView]
        zoom = operator(zoom, float(clientSize[1]) / self.imageShape[1])
        # Pan so that the lower-left corner of the image is in the lower-left
        # corner of our view area.
        self.panX = (clientSize[0] - self.imageShape[1]) / zoom / 2
        self.panY = (clientSize[1] - self.imageShape[0]) / zoom / 2
        self.zoom = zoom
        self.Refresh(0)
