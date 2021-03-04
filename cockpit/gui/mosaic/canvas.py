#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import numpy
from OpenGL.GL import *
import traceback
import wx.glcanvas

from cockpit import events
from cockpit.gui.mosaic.tile import Tile, MegaTile
import cockpit.util.datadoc
import cockpit.util.logger
import cockpit.util.threads
import queue
import time
import numpy as np


## Zoom level at which we switch from rendering megatiles to rendering tiles.
ZOOM_SWITCHOVER = 1
BUFFER_LENGTH = 32


class MosaicCanvas(wx.glcanvas.GLCanvas):
    """Canvas where the mosaic is drawn.

    Mosaics consist of collections of images from the cameras.  This
    class sets up the OpenGL canvas that image data is drawn to.  Has
    a basic level-of-detail system so that the computer doesn't bog
    down horribly when trying to draw thousands of tiles at the same
    time.

    """
    ## Tiles and context are shared amongst all instances, since all
    # offer views of the same data.
    # The first instance creates the context.
    ## List of MegaTiles. These will be created in self.initGL.
    megaTiles = []
    ## List of Tiles. These are created as we receive new images from
    # our parent.
    tiles = []
    ## Set of tiles that need to be rerendered in the next onPaint call.
    tilesToRefresh = set()
    ## WX rendering context
    context = None

    ## \param stageHardLimits An ((xMin, xMax), (yMin, yMax)) tuple
    #         describing the limits of motion, in microns, of the stage.
    # \param overlayCallback Function to call, during rendering, to draw
    #        the overlay on top of the mosaic.
    # \param mouseCallback Function to propagate mouse events to.
    def __init__(self, parent, stageHardLimits, overlayCallback, 
            mouseCallback, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.stageHardLimits = stageHardLimits
        self.overlayCallback = overlayCallback

        ## X and Y translation when rendering.
        self.dx, self.dy = 0.0, 0.0
        ## Scaling factor.
        self.scale = 1.0
        ## Set to True once we've done some initialization.
        self.haveInitedGL = False
        ## WX rendering context
        if MosaicCanvas.context is None:
            # This is the first (and master) instance.
            MosaicCanvas.context = wx.glcanvas.GLContext(self)
            # Hook up onIdle - only one instance needs to process new tiles.
            self.Bind(wx.EVT_IDLE, self.onIdle)

        ## Error that occurred when rendering. If this happens, we prevent
        # further rendering to avoid error spew.
        self.renderError = None

        ## A buffer of images waiting to be added to the mosaic.
        self.pendingImages = queue.Queue(BUFFER_LENGTH)

        self.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_MOUSE_EVENTS, mouseCallback)
        # Do nothing on this event, to avoid flickering.
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: event)
        #event on DPI chnage on high DPI screens, needed for Mac retina
        #displays.
        self.Bind(wx.EVT_DPI_CHANGED, self.onDPIchange)
  


    ## Now that OpenGL's ready to go, perform any necessary initialization.
    # We can now create textures, for example, so it's time to create our 
    # MegaTiles.
    def initGL(self):
        glClearColor(1, 1, 1, 0)

        # Non-zero objective offsets require expansion of area covered
        # by megatiles.
        offsets = [h.offset for h in wx.GetApp().Objectives.GetHandlers()]
        minmax = lambda l: (min(l), max(l))
        xOffLim = minmax([-offset[0] for offset in offsets])
        yOffLim = minmax([offset[1] for offset in offsets])
        (xMin, xMax), (yMin, yMax) = self.stageHardLimits
        # Bounds checks ensure we only increase the megatile area, not
        # decrease it.
        #
        # We need to increase upper limit further so we don't miss tiles at
        # the edges. We should just need to add megaTileMicronSize to each
        # axis to make sure we add tiles up to and including our bounds. This
        # works for the x-axis, but not y. For some reason, we need to add
        # *four* times this value to the y-axis. The megaTile's y-origin is at
        # its centre, whereas the x-origin is at an edge; as far as I can see,
        # but this should require only up to three times the tilesize added to
        # the upper limit, not four.
        # Four works, though.
        # Arrays run [0,0] .. [ncols, nrows]; GL runs (-1,-1) .. (1,1). Since
        # making adjustments to render [0,0] at (-1,1), we now add two megatiles
        # at each y limit, rather than 4 at one edge.
        tsize = glGetInteger(GL_MAX_TEXTURE_SIZE)
        # If we use the full texture size, it seems it's too large for manipul-
        # ation in a framebuffer:
        #   * on Macs with Intel chipsets;
        #   * on some mobile nVidia chipsets.
        # Check vendor with glGetString(GL_VENDOR)
        # GL_MAX_FRAMEBUFFER_WIDTH and _HEIGHT are not universally available,
        # so we just use a quarter of the max texture size or a reasonable
        # upper bound which has been found to work in tests on 2017-ish
        # Macbook Pro.
        tsize = min(tsize // 4, 16384)
        MegaTile.setPixelSize(tsize)
        xMin += min(0, xOffLim[0]) - MegaTile.micronSize
        xMax += max(0, xOffLim[1]) + MegaTile.micronSize
        yMin += min(0, yOffLim[0]) - 2*MegaTile.micronSize
        yMax += max(0, yOffLim[1]) + 2*MegaTile.micronSize
        for x in np.arange(xMin, xMax, MegaTile.micronSize):
            for y in np.arange(yMin, yMax, MegaTile.micronSize):
                self.megaTiles.append(MegaTile((-x, y)))
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
            tile.prerenderTiles(self.tiles)


    ## Delete all tiles and textures, including the megatiles.
    def deleteAll(self):
        self.deleteTilesList(list(self.tiles))
        events.publish(events.MOSAIC_UPDATE)


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
        tileShape = tile.textureData.shape
        # Start with a neutral background based on the tile's mean value.
        result = numpy.ones((tileShape[0] * 3, tileShape[1] * 3), 
                dtype = tile.textureData.dtype) * tile.textureData.mean()

        # Get the bounding box 3x bigger than the tile with the tile at the 
        # center.
        width, height = tile.size
        tileX, tileY, tileZ = tile.pos
        start = (tileX - width, tileY - height)
        end = (tileX + width * 2, tileY + height * 2)
        pixelSize = tile.getPixelSize()
        for altTile in self.getTilesIntersecting(start, end, allowedTiles):
            if altTile.getPixelSize() != pixelSize:
                # Don't try to deal with tiles with differing pixel sizes.
                continue
            # Figure out the portion of altTile that intersects our region.
            xMin = max(start[0], altTile.pos[0])
            xMax = min(end[0], altTile.pos[0] + altTile.size[0])
            yMin = max(start[1], altTile.pos[1])
            yMax = min(end[1], altTile.pos[1] + altTile.size[1])
            xPixels = (xMax - xMin) // pixelSize[0]
            yPixels = (yMax - yMin) // pixelSize[1]
            # Get the offset into altTile, and thus the relevant pixel data.
            altX = (xMin - altTile.pos[0]) / pixelSize[0]
            altY = (yMin - altTile.pos[1]) / pixelSize[1]
            subRegion = altTile.textureData[altX:altX + xPixels, altY:altY + yPixels]
            if 0 in subRegion.shape:
                # The intersection is tangential; unlikely but can happen. 
                # Skip this tile as it doesn't provide useful intersection.
                continue
            # Get the offset into result.
            rX = max(0, (altTile.pos[0] - start[0]) / pixelSize[0])
            rY = max(0, (altTile.pos[1] - start[1]) / pixelSize[1])
            # HACK: for some reason that I don't understand, the above gives
            # me swapped-and-offset X and Y axes. I need to swap them back
            # while accounting for the difference in aspect ratio.
            tX = rY * (float(tileShape[0]) / tileShape[1])
            tY = rX * (float(tileShape[1]) / tileShape[0])
            rX, rY = tX, tY
            target = result[rX:rX + xPixels, rY:rY + yPixels]
            target[:] = subRegion

        return result



    ## Delete all tiles that intersect the specified box.
    def deleteTilesIntersecting(self, start, end):
        self.deleteTilesList(self.getTilesIntersecting(start, end))
        events.publish(events.MOSAIC_UPDATE)
               

    ## Delete a list of tiles.
    @cockpit.util.threads.callInMainThread
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
        events.publish(events.MOSAIC_UPDATE)


    def onIdle(self, event):
        if self.pendingImages.empty():# or not self.IsShownOnScreen():
            return
        # Draw as many images as possible in 50ms.
        t = time.time()
        newTiles = []
        self.SetCurrent(self.context)
        while not self.pendingImages.empty() and (time.time()-t < 0.05):
            data, pos, size, scalings, layer = self.pendingImages.get()
            newTiles.append(Tile(data, pos, size, scalings, layer))
        self.tiles.extend(newTiles)
        for megaTile in self.megaTiles:
            megaTile.prerenderTiles(newTiles)

        self.tilesToRefresh.update(newTiles)

        self.Refresh()
        events.publish(events.MOSAIC_UPDATE)
        if not self.pendingImages.empty():
            event.RequestMore()


    ## Add a new image to the mosaic.
    #@cockpit.util.threads.callInMainThread
    def addImage(self, data, pos, size, scalings=(None, None), layer=0):
        self.pendingImages.put((data, pos, size, scalings, layer))


    ## Rescale the tiles.
    # \param minMax A (blackpoint, whitepoint) tuple, or None to rescale
    # each tile individually.
    @cockpit.util.threads.callInMainThread
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

            width, height = self.GetClientSize()*self.GetContentScaleFactor()

            glViewport(0, 0, width, height)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(-.375, width - .375, -.375, height - .375, 1, -1)
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
        except Exception as e:
            print ("Error rendering the canvas:",e)
            traceback.print_exc()
            self.renderError = e


    ## Change our view transform.
    def zoomTo(self, x, y, scale):
        # Paranoia
        if not scale:
            return
        width, height = self.GetClientSize()*self.GetContentScaleFactor()
        self.dx = -x * scale + width / 2
        self.dy = -y * scale + height / 2
        self.scale = scale
        self.Refresh()


    ## Change our zoom by the specified multiplier. This requires changing
    # our translational offset too to keep the view centered.
    def multiplyZoom(self, multiplier):
        # Paranoia
        if multiplier == 0:
            return
        self.scale *= multiplier
        width, height = self.GetClientSize()*self.GetContentScaleFactor()
        halfWidth = width / 2
        halfHeight = height / 2
        self.dx = halfWidth - (halfWidth - self.dx) * multiplier
        self.dy = halfHeight - (halfHeight - self.dy) * multiplier
        self.Refresh()

    def onDPIchange(self,event):
        #not an ideal solution as visible region changes but
        #recalcs positions etc...
        self.multiplyZoom(1)

    ## Change our translation by the specified number of pixels.
    def dragView(self, offset):
        self.dx += offset[0]
        self.dy -= offset[1]
        self.Refresh()


    ## Remap an (X, Y) tuple of screen coordinates to a location on the stage.
    def mapScreenToCanvas(self, pos):
        scaleFactor = self.GetContentScaleFactor()
        pos = (pos[0]*scaleFactor,pos[1]*scaleFactor)
        
        height = self.GetClientSize()[1]*scaleFactor
        return ((self.dx - pos[0]) / self.scale,
                -(self.dy - height + pos[1]) / self.scale)


    ## Return a (bottom left, top right) tuple showing what part
    # of the stage is currently visible.
    def getViewBox(self):
        width, height = self.GetClientSize()*self.GetContentScaleFactor()
        bottomLeft = (-self.dx / self.scale, -self.dy / self.scale)
        topRight = (-(self.dx - width) / self.scale,
                       -(self.dy - height) / self.scale)
        return (bottomLeft, topRight)


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
        header = cockpit.util.datadoc.makeHeaderFor(imageData)

        handle = open(mrcPath, 'wb')
        cockpit.util.datadoc.writeMrcHeader(header, handle)
        for i, image in enumerate(imageData[:,:]):
            handle.write(image)
            statusDialog.Update(i)
        handle.close()
        statusDialog.Destroy()


    ## Load a text file describing a set of tiles, as well as the tile image
    # data. This is made a bit trickier by the fact that we want to display
    # a progress dialog that updates as new images are added, but addImage()
    # must run in the main thread while we run in a different one ...
    # although maybe not since MAP added a queue and a thread to process
    # new tiles.
    @cockpit.util.threads.callInNewThread
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
                tileStats.append(list(map(float, line.strip().split(','))))
        try:
            doc = cockpit.util.datadoc.DataDoc(mrcPath)
        except Exception as e:
            wx.MessageDialog(self.GetParent(), 
                    message = "I was unable to load the MRC file at\n%s\nholding the tile data. The error message was:\n\n%s\n\nPlease verify that the file path is correct and the file is valid." % (mrcPath, e),
                    style = wx.ICON_INFORMATION | wx.OK).ShowModal()
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
            cockpit.util.logger.log.warning("Loading mosaic with %d images; only have positioning information for %d." % (doc.imageArray.shape[2], len(tileStats)))
        maxImages = min(doc.imageArray.shape[2], len(tileStats))
        for i in range(maxImages):
            image = doc.imageArray[0, 0, i]
            stats = tileStats[i]
            try:
                data = image[:int(stats[5]), :int(stats[6])]
                self.addImage(data, stats[:3], stats[3:5], stats[7:9], 
                            int(stats[9]))
            except Exception as e:
                wx.MessageDialog(self.GetParent(),
                        "Failed to load line %d of file %s: %s.\n\nPlease see the logs for more details." % (i, filePath, e),
                        style = wx.ICON_INFORMATION | wx.OK).ShowModal()
                cockpit.util.logger.log.error(traceback.format_exc())
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
        events.publish(events.MOSAIC_UPDATE)
