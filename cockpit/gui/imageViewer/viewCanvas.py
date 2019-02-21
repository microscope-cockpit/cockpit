#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
## Copyright (C) 2019 Nicholas Hall <nicholas.hall@dtc.ox.ac.uk>
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


from cockpit import events
import cockpit.gui
import cockpit.gui.guiUtils
from . import image
import cockpit.util.threads

from cockpit.util import ftgl
import numpy
from OpenGL.GL import *
from six.moves import queue
import threading
import traceback
import wx
import wx.glcanvas
import operator
from skimage.filters import threshold_otsu
from scipy.ndimage.measurements import center_of_mass
import winsound

## @package cockpit.gui.imageViewer.viewCanvas
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
        self.showAligCentroid = False
        self.showCurCentroid = False
        self.aligCentroidCalculated = False

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
        self.imageQueue = queue.Queue()
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
        self.offsetX = 0
        self.offsetY = 0

        ## What kind of dragging we're doing.
        self.dragMode = DRAG_NONE

        ## Whether or not we've done some one-time initialization work.
        self.haveInitedGL = False

        ## WX context that we set when we need to do GL operations.
        self.context = wx.glcanvas.GLContext(self)

        ## Font for text rendering
        self.font = ftgl.TextureFont(cockpit.gui.FONT_PATH)
        self.font.setFaceSize(18)

        self.Bind(wx.EVT_PAINT, self.onPaint)
        # Do nothing, to prevent flickering
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: 0)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        self.Bind(wx.EVT_MOUSEWHEEL, self.onMouseWheel)
        # Right click also creates context menu event, which will pass up
        # if unhandled. Bind it to None to prevent the main window
        # context menu being displayed after our own.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)

        self.y_alig_cent = None
        self.x_alig_cent = None
        self.y_cur_cent = None
        self.x_cur_cent = None
        self.diff_y = None
        self.diff_x = None

    def onMouseWheel(self, event):
        # Only respond if event originated within window.
        p = event.GetPosition()
        s = self.GetSize()
        if any(map(operator.or_, map(operator.gt, p, s), map(operator.lt, p, (0,0)))):
            return
        rotation = event.GetWheelRotation()
        if rotation:
            self.modZoom(rotation / 1000.0)


    def InitGL(self):
        self.w, self.h = self.GetClientSize()
        self.SetCurrent(self.context)
        glClearColor(0.3, 0.3, 0.3, 0.0)   ## background color

        self.haveInitedGL = True


    ## Stop displaying anything. Optionally destroy the canvas at the end.
    @cockpit.util.threads.callInMainThread
    def clear(self, shouldDestroy = False):
        # Clear out the queue of images.
        while True:
            try:
                self.imageQueue.get_nowait()
            except queue.Empty:
                break
        self.imageData = None
        self.imageShape = None
        self.imageMin = None
        self.imageMax = None
        if self.tileShape is not None:
            for i in range(self.tileShape[0]):
                for j in range(self.tileShape[1]):
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
    @cockpit.util.threads.callInNewThread
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
            if self.showAligCentroid:
                if self.aligCentroidCalculated:
                    pass
                else:
                    self.calcCurCentroid(newImage)
                    self.x_alig_cent = self.x_cur_cent
                    self.y_alig_cent = self.y_cur_cent
                    self.aligCentroidCalculated = True
            if self.showCurCentroid:
                self.calcCurCentroid(newImage)
            self.setTiles(newImage)
            if shouldResetView:
                self.resetView()
            if isFirstImage:
                wx.CallAfter(self.resetPixelScale)
            # Wait for the image to be drawn before we do anything more.
            self.drawEvent.wait()
            self.drawEvent.clear()


    ## Update our tiles, if necessary, because a new image has arrived.
    @cockpit.util.threads.callInMainThread
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
                    for i in range(self.tileShape[0]):
                        for j in range(self.tileShape[1]):
                            self.tiles[i][j].wipe()
                self.tiles = []
                self.tileShape = (width, height)
                haveSetTiles = False
                
            for i in range(self.tileShape[0]):
                if not haveSetTiles:
                    self.tiles.append([])
                xMin = i * self.tileSize
                xMax = min((i + 1) * self.tileSize, self.imageShape[0])
                for j in range(self.tileShape[1]):
                    yMin = j * self.tileSize
                    yMax = min((j + 1) * self.tileSize, self.imageShape[1])
                    subData = imageData[xMin : xMax, yMin : yMax]
                    if not haveSetTiles:
                        self.tiles[i].append(image.Image(subData))
                    else:
                        self.tiles[i][j].updateImage(subData)

            if not haveSetTiles:
                self.changeHistScale(False)
        except Exception as e:
            print ("Failed to set new image:",e)
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
            ((temp-temp.min()) * numBins / dataRange).astype(numpy.int32))

    def calcCurCentroid(self, imageData):
        thresh = threshold_otsu(imageData)
        binaryIm = imageData > thresh
        imageOtsu = imageData * binaryIm

        y_cent, x_cent = center_of_mass(imageOtsu[10:-10, 10:-10])
        self.y_cur_cent = (y_cent + 10)
        self.x_cur_cent = (x_cent + 10)

        if self.y_alig_cent == None or self.x_alig_cent == None:
            pass
        else:
            self.diff_y = self.y_cur_cent - self.y_alig_cent
            self.diff_x = self.x_cur_cent - self.x_alig_cent
            totaldist=(self.diff_y**2+self.diff_x**2)**0.5
            winsound.Beep(5000/totaldist,50)

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
        for i in range(self.tileShape[0]):
            for j in range(self.tileShape[1]):
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
        # Used to query image data for imageMin and imageMax, but could this
        # occasionally hit an indexing error on the first image when images
        # were arriving fast. Just do the simple arithmetic here.
        #return (self.tiles[0][0].imageMin, self.tiles[0][0].imageMax)
        imageRange = (self.imageMax - self.imageMin)
        return (self.blackPoint * imageRange + self.imageMin,
                self.whitePoint * imageRange + self.imageMin)


    ## As above, but the values used to calculate them instead of the
    # absolute pixel values (e.g. (.1, .9) instead of (100, 400).
    def getRelativeScaling(self):
        return (self.blackPoint, self.whitePoint)


    @cockpit.util.threads.callInMainThread
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
                    for i in range(self.tileShape[0]):
                        for j in range(self.tileShape[1]):
                            self.tiles[i][j].refresh()
                self.shouldRefresh = False

                # Apply zoom
                glTranslatef(self.imageShape[1] / 2.0, self.imageShape[0] / 2.0, 0)
                glScalef(self.zoom, self.zoom, 1)
                glTranslatef(-self.imageShape[1] / 2.0, -self.imageShape[0] / 2.0, 0)

                # Apply pan
                glTranslatef(self.panX/self.zoom, self.panY/self.zoom, 0)

                glEnable(GL_TEXTURE_2D)

                # Draw the actual tiles.
                for i in range(self.tileShape[0]):
                    for j in range(self.tileShape[1]):
                        glPushMatrix()
                        glTranslatef(j * self.tileSize, i * self.tileSize, 0)
                        self.tiles[i][j].render()
                        glPopMatrix()

                glDisable(GL_TEXTURE_2D)
                glTranslatef(0, -HISTOGRAM_HEIGHT, 0)
                if self.showCrosshair:
                    self.drawCrosshair()
                if self.showAligCentroid:
                    self.drawCentroidCross(y_cent=self.y_alig_cent, x_cent=self.x_alig_cent,
                                           colour=(0, 255, 255))
                if self.showCurCentroid:
                    self.drawCentroidCross(y_cent=self.y_cur_cent, x_cent=self.x_cur_cent,
                                           colour=(255, 0, 255))
                glPopMatrix()

                self.drawHistogram()


            glFlush()
            self.SwapBuffers()
            self.drawEvent.set()
        except Exception as e:
            print ("Error drawing view canvas:",e)
            traceback.print_stack()
            self.shouldDraw = False


    @cockpit.util.threads.callInMainThread
    def drawCrosshair(self, ):
        glColor3f(0, 255, 255)
        glBegin(GL_LINES)
        glVertex2f(0, HISTOGRAM_HEIGHT + 0.5 * (self.imageShape[0]))
        glVertex2f(self.imageShape[1], HISTOGRAM_HEIGHT +
                   0.5 * (self.imageShape[0]))
        glVertex2f(0.5 * self.imageShape[1], HISTOGRAM_HEIGHT)
        glVertex2f(0.5 * self.imageShape[1], self.imageShape[0]+HISTOGRAM_HEIGHT)
        glEnd()

    @cockpit.util.threads.callInMainThread
    def drawCentroidCross(self, y_cent, x_cent, colour):
        if x_cent == None or y_cent == None:
            return
        glColor3f(colour[0], colour[1], colour[2])
        glBegin(GL_LINES)
        glVertex2f(x_cent - 50, HISTOGRAM_HEIGHT + y_cent)
        glVertex2f(x_cent + 50, HISTOGRAM_HEIGHT + y_cent)
        glVertex2f(x_cent, HISTOGRAM_HEIGHT + y_cent - 50)
        glVertex2f(x_cent, HISTOGRAM_HEIGHT + y_cent + 50)
        glEnd()

    ## Draw the histogram of our data.
    @cockpit.util.threads.callInMainThread
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
        if self.showCurCentroid:
            if self.diff_y == None or self.diff_x == None:
                self.font.render('%d [%s %10d] %d' %
                                 (self.tiles[0][0].imageMin, self.imageMin,
                                  self.imageMax, self.tiles[0][0].imageMax))
            else:
                self.font.render('%d [%s %10d] %d       X dist = %f, Y dist = %f' %
                                 (self.tiles[0][0].imageMin, self.imageMin,
                                  self.imageMax, self.tiles[0][0].imageMax,
                                  self.diff_x, self.diff_y))
        else:
            self.font.render('%d [%s %10d] %d' %
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
                self.Bind(wx.EVT_MENU,  lambda event, action = action: action(), id= id)
            cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)
        elif event.Entering() and self.TopLevelParent.IsActive():
            self.SetFocus()
        else:
            event.Skip()

        # In case current mouse position has changed enough to require
        # redrawing the histogram. A bit wasteful of resources, this.
        wx.CallAfter(self.Refresh)


    ## Generate a list of (label, action) tuples to use for generating menus.
    def getMenuActions(self):
        return [('Reset view', self.resetView),
                ('Fill viewer', lambda: self.resetView(True)),
                ('Set histogram parameters', self.onSetHistogram),
                ('Toggle alignment crosshair', self.toggleCrosshair),
                ('Toggle show aligment centroid', self.toggleAligCentroid),
                ('Toggle show current centroid', self.toggleCurCentroid)]

    ## Let the user specify the blackpoint and whitepoint for image scaling.
    def onSetHistogram(self, event = None):
        values = cockpit.gui.dialogs.getNumberDialog.getManyNumbersFromUser(
                parent = self, title = "Set histogram scale parameters",
                prompts = ["Blackpoint", "Whitepoint"],
                defaultValues = [self.tiles[0][0].imageMin, self.tiles[0][0].imageMax])
        values = [float(v) for v in values]
        # Convert from pixel intensity values to [0, 1] scale values.
        divisor = max(float(self.imageMax - self.imageMin), 1.0)
        self.blackPoint = (values[0] - self.imageMin) / divisor
        self.whitePoint = (values[1] - self.imageMin) / divisor
        self.changeHistScale(shouldRefresh = True)


    def toggleCrosshair(self, event=None):
        self.showCrosshair = not(self.showCrosshair)

    def toggleAligCentroid(self, event=None):
        self.aligCentroidCalculated = False
        self.showAligCentroid = not (self.showAligCentroid)

    def toggleCurCentroid(self, event=None):
        self.showCurCentroid = not (self.showCurCentroid)

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
        oldX=(self.panX-self.offsetX)/self.zoom
        oldY=(self.panY-self.offsetY)/self.zoom
        self.zoom += factor
        if self.zoom <0.001 :
            self.zoom=0.001
        #modify pan variables to keep same position in centre of image.
        self.panX=(oldX*self.zoom+self.offsetX)
        self.panY=(oldY*self.zoom+self.offsetY)
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
        # corner of our view area. Store so we can zoom on field centre
        self.offsetX=(clientSize[0] - self.imageShape[1]) / 2.0
        self.offsetY=(clientSize[1] - self.imageShape[0]) / 2.0
        self.panX = self.offsetX
        self.panY = self.offsetY
        self.zoom = zoom
        self.Refresh(0)
