#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018-19 Mick Phillips <mick.phillips@gmail.com>
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

from cockpit import events
import cockpit.gui
import cockpit.gui.freetype
import cockpit.gui.guiUtils
import cockpit.gui.dialogs.getNumberDialog
import cockpit.util.datadoc
import cockpit.util.threads

from collections.abc import Iterable

import numpy
from OpenGL.GL import *
import numpy as np
import queue
import threading
import traceback
import wx
import wx.glcanvas
import operator


## @package cockpit.gui.imageViewer.viewCanvas
# This module provides a canvas for displaying camera images.

## Display height of the histogram, in pixels
HISTOGRAM_HEIGHT = 40

## Drag modes
(DRAG_NONE, DRAG_CANVAS, DRAG_BLACKPOINT, DRAG_WHITEPOINT) = range(4)


class BaseGL():
    # Default vertex shader glsl source
    _VS = """
    #version 120
    attribute vec2 vXY;
    void main() {
        gl_Position = vec4(vXY, 1, 1);
        gl_FrontColor = gl_Color;
    }
    """
    _FS = None

    @staticmethod
    def _compile_shader(shaderType, source):
        """Compile a glsl shader stage."""
        shader = glCreateShader(shaderType)
        glShaderSource(shader, source)
        glCompileShader(shader)
        result = glGetShaderiv(shader, GL_COMPILE_STATUS)
        if not(result):
            raise RuntimeError(glGetShaderInfoLog(shader))
        return shader

    def getShader(self):
        """Compile and link shader."""
        if not hasattr(self, '_shader'):
            self._shader = glCreateProgram()
            vs = self._compile_shader(GL_VERTEX_SHADER, self._VS)
            glAttachShader(self._shader, vs)
            if self._FS is not None:
                fs = self._compile_shader(GL_FRAGMENT_SHADER, self._FS)
                glAttachShader(self._shader, fs)
            glBindAttribLocation (self._shader, 0, "vXY")
            glLinkProgram(self._shader)
        return self._shader


class Image(BaseGL):
    """ An class for rendering grayscale images from image data.

    GL textures are generated once. GL stores textures as floats with a range of
    0 to 1. We use the data.min and data.max of the incoming data to fill this
    range to prevent loss of detail due to quantisation when rendering low dynamic
    range images.
    """
    # Vertex shader glsl source
    _VS = """
    #version 120
    attribute vec2 vXY;
    uniform float zoom;
    uniform float angle;
    uniform vec2 pan;

    void main() {
        gl_TexCoord[0] = gl_MultiTexCoord0;
        gl_Position = vec4(zoom * (vXY + pan), 1., 1.);
    }
    """
    # Fragment shader glsl source.
    _FS = """
    #version 120
    uniform sampler2D tex;
    uniform float scale;
    uniform float offset;
    uniform bool show_clip;

    void main()
    {
        vec4 lum = clamp(offset + texture2D(tex, gl_TexCoord[0].st) / scale, 0., 1.);
        if (show_clip) {
            gl_FragColor = vec4(0., 0., lum.r == 0, 1.) + vec4(1., lum.r < 1., 1., 1.) * lum.r;
        } else {
            gl_FragColor = vec4(lum.r, lum.r, lum.r, 1.);
        }
    }
    """
    def __init__(self):
        # Maximum texture edge size
        self._maxTexEdge = 0
        # Textures used to display this image.
        self._textures = []
        # New data flag
        self._update = False
        # Geometry as number of textures along each axis.
        self.shape = (0, 0)
        ## Should we use colour to indicate range clipping?
        self.clipHighlight = False
        # Data
        self._data = None
        # Minimum and maximum data value - used for setting greyscale range.
        self.dptp = 1
        self.dmin = 0
        # Grayscale clipping points
        self.vmax = 1
        self.vmin = 0

    @property
    def scale(self):
        return (self.vmax - self.vmin) / (self.dptp)

    @property
    def offset(self):
        return - (self.vmin - self.dmin) / ((self.dptp * self.scale) or 1)

    def __del__(self):
        """Clean up textures."""
        try:
            # On exit, textures may have already been cleaned up.
            glDeleteTextures(len(self._textures), self._textures)
        except:
            pass

    def autoscale(self):
        """Fit grayscale to range covered by data."""
        self.vmin = float(self._data.min())
        self.vmax = float(self._data.max())

    def getDisplayRange(self):
        return (self.vmin, self.vmax)

    def setDisplayRange(self, vmin, vmax):
        """Set offset and scaling given clip points."""
        self.vmin = float(vmin)
        self.vmax = float(vmax)

    def setData(self, data):
        self._data = data
        self._update = True

    def toggleClipHighlight(self, event=None):
        self.clipHighlight = not self.clipHighlight

    def _createTextures(self):
        """Convert data to textures.

        Needs GL context to be set prior to call, and should only
        be called in the main thread."""
        if self._data is None:
            return
        self._maxTexEdge = glGetInteger(GL_MAX_TEXTURE_SIZE)
        data = self._data
        glPixelStorei(GL_UNPACK_SWAP_BYTES, False)
        # Ensure the right number of textures available.
        nx = int(np.ceil(data.shape[1] / self._maxTexEdge))
        ny = int(np.ceil(data.shape[0] / self._maxTexEdge))
        self.shape = (nx, ny)
        ntex = nx * ny
        if ntex > len(self._textures):
            textures = glGenTextures(ntex - len(self._textures))
            if isinstance(textures, Iterable):
                self._textures.extend(textures)
            else:
                self._textures.append(textures)
        elif ntex < len(self._textures):
            glDeleteTextures(len(self._textures) - ntex)
        if ntex == 1:
            # Data will fit into a single texture.
            # Do we need to round these up to a power of 2?
            ty, tx = data.shape
        else:
            # Need to use multiple textures to store data.
            tx = ty = self._maxTexEdge
        self.dptp = data.ptp()
        self.dmin = data.min()
        if self.dptp < 1e-6:
            self.dptp = 1
        for i, tex in enumerate(self._textures):
            xoff = tx * (i % nx)
            yoff = ty * (i // nx)
            subdata = (data[yoff:min(data.shape[0], yoff+ty),
                           xoff:min(data.shape[1], xoff+tx)].astype(np.float32) - self.dmin) / self.dptp
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, tx, ty, 0,
                         GL_RED, GL_FLOAT, None)
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, subdata.shape[1], subdata.shape[0],
                            GL_RED, GL_FLOAT, subdata)
        self._update = False

    def draw(self, pan=(0,0), zoom=1):
        """Render the textures. Caller must set context prior to call."""
        if self._data is None:
            return
        elif self._update:
            self._createTextures()
        shader = self.getShader()
        glUseProgram(shader)
        # Vertical and horizontal modifiers for non-square images.
        hlim = self._data.shape[1] / max(self._data.shape)
        vlim = self._data.shape[0] / max(self._data.shape)
        # Number of x and y textures.
        nx, ny = self.shape
        # Quad dimensions for one texture.
        dx = 2 * hlim / nx
        dy = 2 * vlim / ny
        if len(self._textures) > 1:
            tx = ty = self._maxTexEdge
            # xy & zoom correction for incompletely-filled textures at upper & right edges.
            xcorr = ((tx - self._data.shape[1]) % tx) / (nx * tx)
            ycorr = ((ty - self._data.shape[0]) % ty) / (ny * ty)
            zoomcorr = self._data.shape[1] / (nx * tx)
            zoomcorr = max(zoomcorr, self._data.shape[0] / (ny * ty))
            zoom = zoom / zoomcorr
            pan = (zoomcorr * pan[0] + xcorr, zoomcorr * pan[1] + ycorr )
        # Update shader parameters
        glUniform2f(glGetUniformLocation(shader, "pan"), pan[0], pan[1])
        glUniform1i(glGetUniformLocation(shader, "tex"), 0)
        glUniform1f(glGetUniformLocation(shader, "scale"), self.scale)
        glUniform1f(glGetUniformLocation(shader, "offset"), self.offset)
        glUniform1f(glGetUniformLocation(shader, "zoom"), zoom)
        glUniform1i(glGetUniformLocation(shader, "show_clip"), self.clipHighlight)
        # Render
        glEnable(GL_TEXTURE_2D)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        # nested loops are still quicker than itertools.product
        for j in range(ny):
            # i and j are indices that determine left and bottom quad co-ords.
            # ii and jj determine upper quad co-ords, and may be fractional for
            # quads at the top or right of the image.
            if j > 0 and j == ny - 1:
                jj = self._data.shape[0] / self._maxTexEdge
            else:
                jj = j+1
            for i in range(nx):
                if i > 0 and i == nx - 1:
                    ii = self._data.shape[1] / self._maxTexEdge
                else:
                    ii = i+1
                # Arrays used to create textures have top left at [0,0].
                # GL co-ords run *bottom* left to top right, so need to invert
                # vertical co-ords.
                glVertexPointerf( [(-hlim + i*dx, -vlim + jj*dy),
                                   (-hlim + ii*dx, -vlim + jj*dy),
                                   (-hlim + ii*dx, -vlim + j*dy),
                                   (-hlim + i*dx, -vlim + j*dy)] )
                glTexCoordPointer(2, GL_FLOAT, 0,
                                  [(0, 0), (ii%1 or 1, 0), (ii%1 or 1, jj%1 or 1), (0, jj%1 or 1)])
                glBindTexture(GL_TEXTURE_2D, self._textures[j*nx + i])
                glDrawArrays(GL_QUADS, 0, 4)
        glDisable(GL_TEXTURE_2D)
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glUseProgram(0)


class Histogram(BaseGL):
    def __init__(self):
        self.bins = None
        self.counts = None
        self.lbound = None
        self.ubound = None
        self.lthresh = None
        self.uthresh = None


    def data2gl(self, val):
        return -1 + 2 * (val - self.lbound) / ((self.ubound - self.lbound) or 1)

    def gl2data(self, x):
        return self.lbound + ((self.ubound - self.lbound) or 1) * (x + 1) / 2

    def setData(self, data):
        # Calculate histogram.
        # Use shifted average histogram to avoid binning artefacts.
        # generate set of m histograms
        #   each has class width h
        #   start points 0, h/m, 2h/m, ..., (m-1)h/m
        # 1 < m < 64
        # sum to average
        if self.lbound is None:
            self.lbound = data.min()
        if self.ubound is None:
            self.ubound = data.max()
        if self.lthresh is None:
            self.lthresh = self.lbound
        if self.uthresh is None:
            self.uthresh = self.ubound
        nbins = 64
        m = 4
        self.bins = np.linspace(data.min(), data.max(), nbins)
        self.counts = np.zeros(nbins)
        h = self.bins[1] - self.bins[0]
        for i in range(m):
            these = np.bincount(np.digitize(data.flat, self.bins + i*h/m, right=True), minlength=nbins)
            self.counts += these[0:nbins]

    def draw(self):
        if self.counts is None:
            return
        binw = self.bins[1] - self.bins[0]
        self.lbound = min(self.bins.min()-binw, self.lthresh-binw)
        self.ubound = max(self.bins.max()+binw, self.uthresh+binw)
        w = self.ubound - self.lbound
        glUseProgram(self.getShader())
        v = []
        for (x, y) in zip(self.bins, self.counts):
            x0 = self.data2gl(x)
            x1 = self.data2gl(x + binw)
            h = -1 + 2 * y / (self.counts.max() or 1)
            v.extend( [(x0, -1), (x0, h), (x1, h), (x1, -1)] )
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointerf(v)
        glColor(.8, .8, .8, 1)
        glDrawArrays(GL_QUADS, 0, len(v))
        glColor(1, 0, 0, 1)
        xl = self.data2gl(self.lthresh)
        xu = self.data2gl(self.uthresh)
        dx = 0.05
        glLineWidth(2)
        glVertexPointerf([(xl+dx, -1), (xl, -1), (xl, 1), (xl+dx, 1)])
        glDrawArrays(GL_LINE_STRIP, 0, 4)
        glVertexPointerf([(xu-dx, -1), (xu, -1), (xu, 1), (xu-dx, 1)])
        glDrawArrays(GL_LINE_STRIP, 0, 4)
        glUseProgram(0)


## This class handles displaying multi-channel 2D images.
# Most of the actual drawing logic is handled in the image.Image class.
# It can handle arbitrarily-sized images, by cutting them up into parcels
# and tiling them together.
class ViewCanvas(wx.glcanvas.GLCanvas):
    ## Instantiate.
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.image = Image()
        self.histogram = Histogram()

        ## Menu - keep reference to store state of toggle buttons.
        # Must be created after self.image.
        self._menu = wx.Menu()
        for label, action in self.getMenuActions():
            if not label:
                self._menu.AppendSeparator()
                continue
            id = wx.NewIdRef()
            if label.lower().startswith("toggle"):
                self._menu.AppendCheckItem(id, label)
            else:
                self._menu.Append(id, label)
            self.Bind(wx.EVT_MENU, lambda event, action=action: action(), id=id)

        # Canvas geometry - will be set by InitGL, or setSize.
        self.w, self.h = None, None

        ## We set this to false if there's an error, to prevent OpenGL
        # error spew.
        self.shouldDraw = True

        ## Should we show a crosshair (used for alignment)?
        self.showCrosshair = False

        ## Queue of incoming images that we need to either display or discard.
        self.imageQueue = queue.Queue()
        ## Current image we're working with.
        self.imageData = None
        ## Event that signals that we've finished drawing the current image.
        self.drawEvent = threading.Event()
        # This spawns a new thread.
        self.processImages()
        ## Percentile scaling of min/max based on our histogram.
        self.blackPoint, self.whitePoint = 0.0, 1.0

        ## Size of image we've received, which we use for determining
        # scale.
        self.imageShape = None

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
        self.face = cockpit.gui.freetype.Face(self, 18)

        self.Bind(wx.EVT_PAINT, self.onPaint)
        # Do nothing, to prevent flickering
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: 0)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        self.Bind(wx.EVT_MOUSEWHEEL, self.onMouseWheel)
        self.Bind(wx.EVT_DPI_CHANGED, self.onDPIchange)
        # Right click also creates context menu event, which will pass up
        # if unhandled. Bind it to None to prevent the main window
        # context menu being displayed after our own.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)
        self.painting = False

        # Initialise FFT variables
        self.showFFT = False

    def onDPIchange(self,event):
        #rescale the glcanvas object if needed
        self.w, self.h = self.GetClientSize()*self.GetContentScaleFactor()

    def onMouseWheel(self, event):
        # Only respond if event originated within window.
        p = event.GetPosition()
        s = self.GetSize()*self.GetContentScaleFactor()
        if any(map(operator.or_, map(operator.gt, p, s), map(operator.lt, p, (0,0)))):
            return
        rotation = event.GetWheelRotation()
        if not rotation:
            return
        factor = rotation / 1000.
        x, y = event.GetLogicalPosition(wx.ClientDC(self))
        w, h = self.GetClientSize()*self.GetContentScaleFactor()
        h -= HISTOGRAM_HEIGHT*self.GetContentScaleFactor()
        glx = -(2 * (x / w) - 1) / self.zoom
        gly = (2 * (y / h) - 1) / self.zoom
        newZoom = self.zoom * (1 + factor)
        if newZoom < 0.001:
            factor = -1 + 0.001 / self.zoom
            newZoom = 0.001
        self.zoom = newZoom
        self.panX += factor * glx
        self.panY += factor * gly
        self.Refresh()


    def InitGL(self):
        self.w, self.h = self.GetClientSize()*self.GetContentScaleFactor()
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
            self.histogram.setData(newImage)
            if self.showFFT:
                self.image.setData(np.log(np.abs(np.fft.fftshift(np.fft.fft2(self.imageData))) + 1e-16))
            else:
                self.image.setData(newImage)
            if shouldResetView:
                self.resetView()
            if isFirstImage:
                self.image.autoscale()
            wx.CallAfter(self.Refresh)
            # Wait for the image to be drawn before we do anything more.
            self.drawEvent.wait()
            self.drawEvent.clear()


    ## Return the blackpoint and whitepoint (i.e. the pixel values which
    # are displayed as black and white, respectively).
    def getScaling(self):
        if self.imageData is None:
            # No image to operate on yet.
            return (None, None)
        else:
            return self.image.getDisplayRange()


    ## As above, but the values used to calculate them instead of the
    # absolute pixel values (e.g. (.1, .9) instead of (100, 400).
    def getRelativeScaling(self):
        return (self.blackPoint, self.whitePoint)


    #@cockpit.util.threads.callInMainThread
    def onPaint(self, event):
        if not self.shouldDraw:
            return

        try:
            # Unused, but wx requires we create an instance of PaintDC.
            dc = wx.PaintDC(self)
        except:
            return

        if not self.haveInitedGL:
            self.InitGL()

        if self.painting:
            print("Concurrent - returning")
            return

        try:
            Hist_Height=int(HISTOGRAM_HEIGHT*self.GetContentScaleFactor())
            self.painting = True
            self.SetCurrent(self.context)
            glClear(GL_COLOR_BUFFER_BIT)
            glViewport(0, Hist_Height,
                       self.w, self.h - Hist_Height)
            self.image.draw(pan=(self.panX, self.panY), zoom=self.zoom)
            if self.showCrosshair:
                self.drawCrosshair()


            glViewport(0, 0, self.w, Hist_Height//2)
            self.histogram.draw()
            glColor(0, 1, 0, 1)

            glViewport(0, 0, self.w, self.h)
            glMatrixMode (GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity ()
            glOrtho (0, self.w, 0, self.h, 1., -1.)
            glTranslatef(0, (Hist_Height)/2+2, 0)
            try:
                self.face.render('%d [%-10d %10d] %d' %
                                 (self.image.dmin, self.histogram.lthresh,
                                  self.histogram.uthresh,
                                  self.image.dmin+self.image.dptp))
            except:
                pass
            glPopMatrix()

            #self.drawHistogram()

            #glFlush()
            self.SwapBuffers()
            self.drawEvent.set()
        except Exception as e:
            print ("Error drawing view canvas:",e)
            traceback.print_exc()
            #self.shouldDraw = False
        finally:
            self.painting = False


    @cockpit.util.threads.callInMainThread
    def drawCrosshair(self):
        glColor3f(0, 255, 255)
        glVertexPointerf([(-1, self.zoom*self.panY), (1, self.zoom*self.panY),
                          (self.zoom*self.panX, -1), (self.zoom*self.panX, 1)])
        glDrawArrays(GL_LINES, 0, 4)


    ## Update the size of the canvas by scaling it.
    def setSize(self, size):
        if self.imageData is not None:
            self.w, self.h = size*self.GetContentScaleFactor()
        self.Refresh(0)


    def onMouse(self, event):
        if self.imageShape is None:
            return
        self.curMouseX, self.curMouseY = (event.GetPosition() *
                                          self.GetContentScaleFactor())
        self.updateMouseInfo(self.curMouseX, self.curMouseY)
        if event.LeftDClick():
            # Explicitly skip EVT_LEFT_DCLICK for parent to handle.
            event.ResumePropagation(2)
            event.Skip()
        elif event.LeftDown():
            # Started dragging
            self.mouseDragX, self.mouseDragY = self.curMouseX, self.curMouseY
            blackPointX = 0.5 * (1+self.histogram.data2gl(self.histogram.lthresh)) * self.w
            whitePointX = 0.5 * (1+self.histogram.data2gl(self.histogram.uthresh)) * self.w
            # Set drag mode based on current window position
            if self.h - self.curMouseY >= (HISTOGRAM_HEIGHT *
                                           self.GetContentScaleFactor()* 2):
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
                # user expects.
                self.modPan(self.curMouseX - self.mouseDragX,
                            self.mouseDragY - self.curMouseY)
            elif self.dragMode in [DRAG_BLACKPOINT, DRAG_WHITEPOINT]:
                glx = -1 + 2 * self.curMouseX / self.w
                threshold = self.histogram.gl2data(glx)
                if self.dragMode == DRAG_BLACKPOINT:
                    self.histogram.lthresh = threshold
                    self.image.vmin = threshold
                else:
                    self.histogram.uthresh = threshold
                    self.image.vmax = threshold
            self.mouseDragX = self.curMouseX
            self.mouseDragY = self.curMouseY
        elif event.RightDown():
            cockpit.gui.guiUtils.placeMenuAtMouse(self, self._menu)
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
                ('Set histogram parameters', self.onSetHistogram),
                ('Toggle clip highlighting', self.image.toggleClipHighlight),
                ('', None),
                ('Toggle alignment crosshair', self.toggleCrosshair),
                ("Toggle FFT mode", self.toggleFFT),
                ('', None),
                ('Save image', self.saveData)
                ]


    ## Let the user specify the blackpoint and whitepoint for image scaling.
    def onSetHistogram(self, event = None):
        values = cockpit.gui.dialogs.getNumberDialog.getManyNumbersFromUser(
            parent = self, title = "Set histogram scale parameters",
            prompts = ["Blackpoint", "Whitepoint"],
            defaultValues = [self.histogram.lthresh, self.histogram.uthresh])
        values = [float(v) for v in values]
        self.image.vmin = self.histogram.lthresh = values[0]
        self.image.vmax = self.histogram.uthresh = values[1]
        self.Refresh()


    def toggleCrosshair(self, event=None):
        self.showCrosshair = not(self.showCrosshair)


    def toggleFFT(self, event=None):
        if self.showFFT:
            self.showFFT = False
            self.image.setData(self.imageData)
        else:
            self.showFFT = True
            self.image.setData(np.log(np.abs(np.fft.fftshift(np.fft.fft2(self.imageData))) + 1e-16))


    ## Convert window co-ordinates to gl co-ordinates.
    def canvasToGl(self, x, y):
        glx = (-1 + 2 *x / self.w - self.panX * self.zoom) / self.zoom
        gly = -(-1 + 2 * y / (self.h - (HISTOGRAM_HEIGHT*
                                        self.GetContentScaleFactor()))
                + self.panY * self.zoom) / self.zoom
        return (glx, gly)


    ## Convert gl co-ordinates to indices into the data.
    # Note: pass in x,y, but returns row-major datay, datax
    def glToIndices(self, glx, gly):
        datax = (1 + glx) * self.imageShape[1] // 2
        datay = self.imageShape[0]-((1 + gly) * self.imageShape[0] // 2)
        return (datay, datax)


    ## Convert window co-ordinates to indices into the data.
    def canvasToIndices(self, x, y):
        return self.glToIndices(*self.canvasToGl(x, y))


    ## Display information on the pixel under the mouse at the given
    # position.
    def updateMouseInfo(self, x, y):
        # Test that all required values have been populated. Use any(...),
        # because ```if None in [...]:``` will throw an exception when an
        # element in the list is an array with more than one element.
        if any(req is None for req in [self.imageData, self.imageShape,
                                       self.w, self.h]):
            return
        # First we have to convert from screen- to data-coordinates.
        coords = numpy.array(self.canvasToIndices(x, y), dtype=np.uint)
        shape = numpy.array(self.imageShape, dtype=np.uint)
        if (coords < shape).all() and (coords >= 0).all():
            value = self.imageData[coords[0], coords[1]]
            events.publish("image pixel info", coords[::-1], value)


    ## Modify our panning amount by the provided factor.
    def modPan(self, dx, dy):
        self.panX += 2 * dx / (self.w * self.zoom)
        self.panY += 2 * dy / (self.h * self.zoom)
        self.Refresh(0)


    ## Reset our view mods.
    def resetView(self):
        if self.imageShape is None:
            # No image to work with.
            return
        self.panX = 0
        self.panY = 0
        self.zoom = 1.0
        self.Refresh(0)

    def resetPixelScale(self):
        self.image.autoscale()
        self.histogram.lthresh, self.histogram.uthresh = self.image.getDisplayRange()
        self.Refresh()

    def saveData(self, evt=None):
        with wx.FileDialog(self, "Save image", wildcard="DV files (*.dv)|*.dv",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
            if fileDialog.ShowModal() != wx.ID_OK:
                return
            path = fileDialog.GetPath()
        # TODO: add XYsize and wavelength to saved data. These can be passed as
        # kwargs, but the way per-camera pixel sizes are handled needs to be
        # addressed first. See issue #538.
        if self.Parent.Parent.curCamera is not None:
            wls = [self.Parent.Parent.curCamera.wavelength,]
        cockpit.util.datadoc.writeDataAsMrc(self.imageData, path, wavelengths=wls)
