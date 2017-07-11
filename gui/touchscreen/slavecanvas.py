#This is based on canvas.py but removed the tile functions to use
#those from the mian canvas. It assumes that a main MoasicCanvas has
#already been created and uses the openGL texture data stored in the
#main canvas but uses its own functions for almost everything else.
#IMD 20160510

import numpy
from OpenGL.GL import *
import time
import traceback
import wx.glcanvas

import events
import gui.mosaic.tile as tile
import util.datadoc
import util.logger
import util.threads
import gui.mosaic.window
import depot

import interfaces.stageMover

## Zoom level at which we switch from rendering megatiles to rendering tiles.
ZOOM_SWITCHOVER = 1

##how good a circle to draw
CIRCLE_SEGMENTS = 32
PI = 3.141592654

## This class handles drawing the mosaic. Mosaics consist of collections of
# images from the cameras.
class SlaveCanvas(wx.glcanvas.GLCanvas):
    ## \param stageHardLimits An ((xMin, xMax), (yMin, yMax)) tuple
    #         describing the limits of motion, in microns, of the stage.
    # \param overlayCallback Function to call, during rendering, to draw
    #        the overlay on top of the mosaic.
    # \param mouseCallback Function to propagate mouse events to.
    def __init__(self, parent, stageHardLimits, overlayCallback,
            mouseCallback, *args, **kwargs):
        wx.glcanvas.GLCanvas.__init__(self, parent, *args, **kwargs)

        self.stageHardLimits = stageHardLimits
        self.overlayCallback = overlayCallback

        ## Width and height of the canvas, in pixels.
        self.width = self.height = None
        ## X and Y translation when rendering.
        self.dx, self.dy = 0.0, 0.0
        ## Scaling factor.
        self.scale = 1.0

        #objective offsets
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.offset = objective.getOffset()
        #stage position variables
        self.curStagePosition = numpy.zeros(3)
        self.prevStagePosition = self.curStagePosition

        events.subscribe("stage position", self.onMotion)


        ## Set to True once we've done some initialization.
        self.haveInitedGL = False
        ## Controls whether we rerender tiles during our onPaint.
        self.shouldRerender = True
        #get a refernce to the master canvas to access the openGL calls.
        self.masterCanvas=gui.mosaic.window.window.canvas
        #this assumes that mastercanvas has already init'd
        ## WX rendering context
        self.context = self.masterCanvas.context


#        #OpenGL tiles are defined by the master mosaic canvas.
#        ## List of MegaTiles. These will be created in self.initGL.
#        self.megaTiles = []
#        ## List of Tiles. These are created as we receive new images from
#        # our parent.
#        self.tiles = []
#        ## Set of tiles that need to be rerendered in the next onPaint call.
#        self.tilesToRefresh = set()

        ## Error that occurred when rendering. If this happens, we prevent
        # further rendering to avoid error spew.
        self.renderError = None

        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_MOUSE_EVENTS, mouseCallback)
        # Do nothing on this event, to avoid flickering.
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: event)


    ## Now that OpenGL's ready to go, perform any necessary initialization.
    # We can now create textures, for example, so it's time to create our
    # MegaTiles.
    def initGL(self):
        self.width, self.height = self.GetClientSize()
        glClearColor(1, 1, 1, 0)
        #tiles defined by main mosaic canvas.
        #        for x in xrange(self.stageHardLimits[0][0], self.stageHardLimits[0][1],
#                tile.megaTileMicronSize):
#            for y in xrange(self.stageHardLimits[1][0], self.stageHardLimits[1][1],
#                    tile.megaTileMicronSize):
#                self.megaTiles.append(tile.MegaTile((-x, y)))
        self.haveInitedGL = True


    ## Because tiles have been changed, we must now rerender all of
    # our megatiles. Don't do this often, and definitely not when
    # other threads need attention.
    # \param tiles Which tiles to rerender. Default to rerendering all.
    def rerenderMegatiles(self, tiles = None):
        self.SetCurrent(self.context)
        if tiles is None:
            tiles = self.masterCanvas.megaTiles
        for tile in self.masterCanvas.tiles:
            self.masterCanvas.tile.recreateTexture()
            self.masterCanvas.tile.prerenderTiles(self.masterCanvas.tiles, self)


    ## Delete all tiles and textures, including the megatiles.
    def deleteAll(self):
        self.masterCanvas.deleteTilesList(list(self.masterCanvas.tiles))


    ## Generate a composite array of tile data surrounding the provided
    # tile, pulling only from the provided list of allowed tiles (or all
    # tiles, if no list is provided).
    def getCompositeTileData(self, tile, allowedTiles = None):
        return (self.deleteTilesList(list(tile,allowedTiles=allowedTiles)))



    ## Delete all tiles that intersect the specified box.
    def deleteTilesIntersecting(self, start, end):
        self.masterCanvas.deleteTilesList(
            self.masterCanvas.getTilesIntersecting(start, end))


    ## Paint the canvas -- in other words, paint all tiles, plus whatever
    # overlays we need.
    def onPaint(self, event):
        if self.renderError is not None:
            return

        try:
            dc = wx.PaintDC(self)
            self.SetCurrent(self.context)
            if not self.haveInitedGL:
                self.initGL()

            glViewport(0, 0, self.width, self.height)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(-.375, (self.width) - .375, -.375, self.height - .375, 1, -1)
            glMatrixMode(GL_MODELVIEW)

            #Dont need this code as it is done in the main mosaic
#            for tile in gui.mosaic.window.window.canvas.tilesToRefresh:
#                self.masterCanvas.tile.refresh()
#            self.tilesToRefresh = set()

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glTranslated(self.dx, self.dy, 0)
            glScaled(self.scale, self.scale, 1)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            ## Paint the megatiles if we're zoomed out, or the
            # normal tiles if we're zoomed in.
            glEnable(GL_TEXTURE_2D)
            viewBox = self.getViewBox()
            if self.scale < ZOOM_SWITCHOVER:
                for megaTile in self.masterCanvas.megaTiles:
                    megaTile.render(viewBox)
            else:
                for tile in self.masterCanvas.tiles:
                    tile.render(viewBox)
            glDisable(GL_TEXTURE_2D)

            if self.overlayCallback is not None:
                self.overlayCallback()

            glFlush()
            self.SwapBuffers()
            events.publish('mosaic canvas paint')

        except Exception, e:
            print "Error rendering the canvas:",e
            traceback.print_exc()
            self.renderError = e




    def onMotion(self, axis, position):
        self.curStagePosition[axis] = position
        self.Refresh()

    ## Change our view transform.
    def zoomTo(self, x, y, scale):
        # Paranoia
        if not scale:
            return
        self.dx = -x * scale + self.width / 2
        self.dy = -y * scale + self.height / 2
        self.scale = scale
        self.Refresh()


    ## Change our zoom by the specified multiplier. This requires changing
    # our translational offset too to keep the view centered.
    def multiplyZoom(self, multiplier):
        # Paranoia
        if multiplier == 0:
            return
        self.scale *= multiplier
        halfWidth = self.width / 2
        halfHeight = self.height / 2
        self.dx = halfWidth - (halfWidth - self.dx) * multiplier
        self.dy = halfHeight - (halfHeight - self.dy) * multiplier
        self.Refresh()


    ## Change our translation by the specified number of pixels.
    def dragView(self, offset):
        self.dx += offset[0]
        self.dy -= offset[1]
        self.Refresh()


    ## Remap an (X, Y) tuple of screen coordinates to a location on the stage.
    def mapScreenToCanvas(self, pos):
        return ((self.dx - pos[0]) / self.scale,
                -(self.dy - self.height + pos[1]) / self.scale)


    ## Return a (bottom left, top right) tuple showing what part
    # of the stage is currently visible.
    def getViewBox(self):
        bottomLeft = (-self.dx / self.scale, -self.dy / self.scale)
        topRight = (-(self.dx - self.width) / self.scale,
                       -(self.dy - self.height) / self.scale)
        return (bottomLeft, topRight)


    ## Toggle display of the specified layer
    def toggleLayer(self, layer, isHidden):
        if isHidden:
            self.m_noShowLayers.add(layer)
        elif layer in self.m_noShowLayers:
            self.m_noShowLayers.remove(layer)


    ## Accept a new size.
    def setSize(self, size):
        self.width, self.height = size
        self.Refresh()


    ## Return our list of Tiles.
    def getTiles(self):
        return self.masterCanvas.tiles
