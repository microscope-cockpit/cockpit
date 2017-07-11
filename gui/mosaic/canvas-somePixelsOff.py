import numpy
from OpenGL.GL import *
import time
import traceback
import wx.glcanvas

import tile
import util.datadoc
import util.logger
import util.threads

## Zoom level at which we switch from rendering megatiles to rendering tiles.
ZOOM_SWITCHOVER = 1

## This class handles drawing the mosaic. Mosaics consist of collections of 
# images from the cameras.
class MosaicCanvas(wx.glcanvas.GLCanvas):
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

        ## Set to True once we've done some initialization.
        self.haveInitedGL = False
        ## Controls whether we rerender tiles during our onPaint.
        self.shouldRerender = True
        ## WX rendering context
        self.context = wx.glcanvas.GLContext(self)

        ## List of MegaTiles. These will be created in self.initGL.
        self.megaTiles = []
        ## List of Tiles. These are created as we receive new images from
        # our parent.
        self.tiles = []
        ## Set of tiles that need to be rerendered in the next onPaint call.
        self.tilesToRefresh = set()

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
        for x in xrange(self.stageHardLimits[0][0], self.stageHardLimits[0][1], 
                tile.megaTileMicronSize):
            for y in xrange(self.stageHardLimits[1][0], self.stageHardLimits[1][1], 
                    tile.megaTileMicronSize):
                self.megaTiles.append(tile.MegaTile((-x, y)))
        self.haveInitedGL = True


    ## Because tiles have been changed, we must now rerender all of
    # our megatiles. Don't do this often, and definitely not when
    # other threads need attention.
    # \param tiles Which tiles to rerender. Default to rerendering all.
    def rerenderMegatiles(self, tiles = None):
        self.SetCurrent(self.context)
        if tiles is None:
            tiles = self.megaTiles
        for tile in tiles:
            tile.recreateTexture()
            tile.prerenderTiles(self.tiles, self)


    ## Delete all tiles and textures, including the megatiles.
    def deleteAll(self):
        self.clearIdx(0, len(self.tiles), refresh = False,
                      shouldRerender = False)
        for tile in self.megaTiles:
            tile.wipe()
        tile.clearFramebuffer()


    ## Get all tiles that intersect the specified box, pulling from the provided
    # list, or from all tiles if no list is provided.
    def getTilesIntersecting(self, start, end, allowedTiles = None):
        if allowedTiles is None:
            allowedTiles = self.tiles
        x1 = min(start[0], end[0])
        x2 = max(start[0], end[0])
        y1 = min(start[1], end[1])
        y2 = max(start[1], end[1])
        start = (x1, y1)
        end = (x2, y2)
        tiles = []
        for tile in allowedTiles:
            if tile.intersectsBox((start, end)):
                tiles.append(tile)
        return tiles


    ## Generate a composite array of tile data surrounding the provided 
    # tile, pulling only from the provided list of allowed tiles (or all
    # tiles, if no list is provided).
    def getCompositeTileData(self, tile, allowedTiles = None):
        if allowedTiles is None:
            allowedTiles = self.tiles
        # Note that we have some axis confusion to deal with here:
        # Tile.textureData and Tile.size are in (Y, X) order, while
        # Tile.pos is in (X, Y, Z) order. 
        tileShape = tile.textureData.shape
        result = numpy.ones((tileShape[0] * 3, tileShape[1] * 3), 
##                dtype = tile.textureData.dtype) * tile.textureData.mean()
                dtype = tile.textureData.dtype) * 1000
        print "Result shape is",result.shape,"compare",tileShape,tile.size,tile.pos
        # pixelSize is similarly flipped to (Y, X) order.
        pixelSize = tile.getPixelSize()
        print "Pixel size is",pixelSize,"giving result array size",result.shape[0]*pixelSize[0],result.shape[1]*pixelSize[1]
        # Get the bounding box 3x bigger than the tile with the tile at the 
        # center.
        height, width = tile.size
        tileX, tileY, tileZ = tile.pos
        start = (tileX - width, tileY - height)
        end = (tileX + width * 2, tileY + height * 2)
        print "Start is at",start,"size is",(end[0] - start[0], end[1] - start[1])
        for altTile in self.getTilesIntersecting(start, end, allowedTiles):
            if altTile.getPixelSize() != pixelSize:
                # Don't try to deal with tiles with differing pixel sizes.
                continue
            print "Alt's size is",altTile.size,"and position",altTile.pos
            # Figure out the portion of altTile that intersects our region.
            xMin = max(start[0], altTile.pos[0])
            xMax = min(end[0], altTile.pos[0] + altTile.size[1])
            yMin = max(start[1], altTile.pos[1])
            yMax = min(end[1], altTile.pos[1] + altTile.size[0])
            xPixels = int((xMax - xMin) / pixelSize[1])
            yPixels = int((yMax - yMin) / pixelSize[0])
            print "Intersection is from",xMin,yMin,"to",xMax,yMax,"giving pixels",xPixels,yPixels
            # Get the offset into altTile, and thus the relevant pixel data.
            altX = (xMin - altTile.pos[0]) / pixelSize[1]
            altY = (yMin - altTile.pos[1]) / pixelSize[0]
            subRegion = altTile.textureData[altY:altY + yPixels, altX:altX + xPixels]
            print "Position in alt is",altX,altY,"giving subRegion shape",subRegion.shape
            # Get the offset into result.
            rX = max(0, (altTile.pos[0] - start[0]) / pixelSize[1])
            rY = max(0, (altTile.pos[1] - start[1]) / pixelSize[0])
            target = result[rY:rY + yPixels, rX:rX + xPixels]
            print "--Position in result is",rX,rY,xPixels,yPixels,"giving target shape",target.shape
            target[:] = subRegion
        test = numpy.copy(result).astype(numpy.uint16)
##        test[:,tileShape[0] - 1:tileShape[0] + 2] = 1000
##        test[tileShape[1] - 1:tileShape[1] + 2] = 1000
##        test[:,tileShape[0] * 2 - 1:tileShape[0] * 2 + 2] = 1000
##        test[tileShape[1] * 2 - 1:tileShape[1] * 2 + 2] = 1000
        import util.datadoc
        util.datadoc.writeDataAsMrc(test, "%s.mrc" % tile.pos)

        return result



    ## Delete all tiles that intersect the specified box.
    def deleteTilesIntersecting(self, start, end):
        self.deleteTilesList(self.getTilesIntersecting(start, end))


    ## Delete a list of tiles.
    @util.threads.callInMainThread
    def deleteTilesList(self, tilesToDelete):
        for tile in tilesToDelete:
            tile.wipe()
            del self.tiles[self.tiles.index(tile)]
        self.SetCurrent(self.context)

        # Rerender all megatiles that are now invalid.
        dirtied = []
        for megaTile in self.megaTiles:
            for tile in tilesToDelete:
                if megaTile.intersectsBox(tile.box):
                    dirtied.append(megaTile)
                    break
        self.rerenderMegatiles(dirtied)
        self.Refresh()


    ## Add a new image to the mosaic.
    @util.threads.callInMainThread
    def addImage(self, data, pos, size, scalings = (None, None), 
            layer = 0, shouldRefresh = False):

        pos = numpy.asarray(pos)
        size = numpy.asarray(size)

        self.SetCurrent(self.context)

        newTile = tile.Tile(data, pos, size, scalings, layer)
        self.tiles.append(newTile)
        for megaTile in self.megaTiles:
            megaTile.prerenderTiles([newTile], self)

        if not shouldRefresh:
            self.shouldRerender = True
            self.tilesToRefresh.add(newTile)
            self.Refresh()


    ## Rescale the tiles.
    # \param minMax A (blackpoint, whitepoint) tuple, or None to rescale
    # each tile individually.
    @util.threads.callInMainThread
    def rescale(self, minMax = None):
        if minMax is None:
            # Tiles will treat this as "use our own data".
            minMax = (None, None)
        for tile in self.tiles:
            tile.scaleHistogram(*minMax)
        self.tilesToRefresh.update(self.tiles)
        self.rerenderMegatiles()
        self.Refresh()


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
            glOrtho(-.375, self.width - .375, -.375, self.height - .375, 1, -1)
            glMatrixMode(GL_MODELVIEW)

            for tile in self.tilesToRefresh:
                tile.refresh()
            self.tilesToRefresh = set()

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
                for megaTile in self.megaTiles:
                    megaTile.render(viewBox)
            else:
                for tile in self.tiles:
                    tile.render(viewBox)
            glDisable(GL_TEXTURE_2D)

            if self.overlayCallback is not None:
                self.overlayCallback()

            glFlush()
            self.SwapBuffers()
        except Exception, e:
            print "Error rendering the canvas:",e
            traceback.print_exc()
            self.renderError = e


    ## Change our view transform.
    def zoomTo(self, x, y, scale):
        self.dx = -x * scale + self.width / 2
        self.dy = -y * scale + self.height / 2
        self.scale = scale
        self.Refresh()


    ## Change our zoom by the specified multiplier. This requires changing
    # our translational offset too to keep the view centered.
    def multiplyZoom(self, multiplier):
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


    ## Given a path to a file, save the mosaic to that file and an adjacent
    # file. The first is a text file that describes the layout of the tiles;
    # the second is an MRC file that holds the actual image data.
    def saveTiles(self, savePath):
        statusDialog = wx.ProgressDialog(parent = self.GetParent(),
                title = "Saving...",
                message = "Saving mosaic image data...", 
                maximum = len(self.tiles))
        handle = open(savePath, 'w')
        mrcPath = savePath + '.mrc'
        if '.txt' in savePath:
            mrcPath = savePath.replace('.txt', '.mrc')
        handle.write("%s\n" % mrcPath)
        width = 0
        height = 0
        for tile in self.tiles:
            width = max(width, tile.textureData.shape[0])
            height = max(height, tile.textureData.shape[1])
            # We do this by a series of extensions since some of these lists
            # may be Numpy arrays, which don't do array extension when you
            # "add" them.
            values = []
            values.extend(tile.pos)
            values.extend(tile.size)
            values.extend(tile.textureData.shape)
            values.extend(tile.histogramScale)
            values.append(tile.layer)
            values = map(str, values)
            handle.write(','.join(values) + '\n')
        handle.close()

        # Now we have the max image extent in X and Y, we can pile everything
        # into a single array for saving as an MRC file. Images smaller than
        # the max will be padded with zeros.
        imageData = numpy.zeros((1, 1, len(self.tiles), width, height),
                dtype = numpy.uint16)
        for i, tile in enumerate(self.tiles):
            imageData[0, 0, i, :tile.textureData.shape[0], :tile.textureData.shape[1]] = tile.textureData
        header = util.datadoc.makeHeaderFor(imageData, 0, 0)

        handle = open(mrcPath, 'wb')
        util.datadoc.writeMrcHeader(header, handle)
        for i, image in enumerate(imageData[:,:]):
            handle.write(image)
            statusDialog.Update(i)
        handle.close()
        statusDialog.Destroy()


    ## Load a text file describing a set of tiles, as well as the tile image
    # data. This is made a bit trickier by the fact that we want to display
    # a progress dialog that updates as new images are added, but addImage()
    # must run in the main thread while we run in a different one. 
    @util.threads.callInNewThread
    def loadTiles(self, filePath):
        with open(filePath, 'r') as handle:
            mrcPath = handle.readline().strip()
            tileStats = []
            for line in handle:
                # X position, Y position, Z position, 
                # X micron size, Y micron size,
                # X pixel size, Y pixel size, blackpoint, whitepoint, layer.
                # We'll have to convert the pixel sizes and layer to
                # ints later.
                tileStats.append(map(float, line.strip().split(',')))
        numInitialTiles = len(self.tiles)
        try:
            doc = util.datadoc.DataDoc(mrcPath)
        except Exception, e:
            wx.MessageDialog(self.GetParent(), 
                    message = "I was unable to load the MRC file at %s holding the tile data. The error message was:\n\n%s\n\nPlease verify that the file path is correct and the file is valid." % (mrcPath, e),
                    style = wx.ICON_EXCLAMATION | wx.STAY_ON_TOP | wx.OK).ShowModal()
            return
        # NOTE: this dialog is not safe to Update, since the update calls must
        # be referred to the main thread (via wx.CallAfter) and may arrive
        # in an unpredictable order. Due to the unpredictable order, the call
        # to Destroy (which must also happen in the main thread via CallAfter)
        # may arrive before all of the Update calls are processed, resulting
        # in a segfault.
        statusDialog = wx.ProgressDialog(parent = self.GetParent(),
                title = "Loading...",
                message = "Loading mosaic image data...")
        statusDialog.Show()
        if doc.imageArray.shape[2] > len(tileStats):
            # More images in the file than we have stats for.
            util.logger.log.warn("Loading mosaic with %d images; only have positioning information for %d." % (doc.imageArray.shape[2], len(tileStats)))
        maxImages = min(doc.imageArray.shape[2], len(tileStats))
        for i in xrange(maxImages):
            image = doc.imageArray[0, 0, i]
            stats = tileStats[i]
            try:
                data = image[:int(stats[5]), :int(stats[6])]
                self.addImage(data, stats[:3], stats[3:5], stats[7:9], 
                            int(stats[9]))
            except Exception, e:
                wx.MessageDialog(self.GetParent(),
                        "Failed to load line %d of file %s: %s.\n\nPlease see the logs for more details." % (i, filePath, e),
                        style = wx.ICON_INFORMATION | wx.OK).ShowModal()
                util.logger.log.error(traceback.format_exc())
                statusDialog.Destroy()
                return
        # Wait until we've loaded all tiles or we go a full second without
        # any new tiles arriving.
        numExpectedTiles = len(self.tiles) + len(tileStats)
        lastUpdatedTime = time.time()
        curCount = len(self.tiles)
        while len(self.tiles) != numExpectedTiles:
            count = len(self.tiles)
            if count != curCount:
                lastUpdatedTime = time.time()
                curCount = count
            if time.time() - lastUpdatedTime > 1:
                break
            time.sleep(.1)
        wx.CallAfter(statusDialog.Destroy)


    ## Return our list of Tiles.
    def getTiles(self):
        return self.tiles
