#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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

"""
Handles display of a single tile in the canvas.  A tile is either a
single image from one camera, or a larger array of low-resolution
images from that camera; the latter is used when zoomed out, as a
performance measure.

"""

import numpy
from OpenGL.GL import (
    GL_BLUE_BIAS,
    GL_BLUE_SCALE,
    GL_CLAMP,
    GL_COLOR_ATTACHMENT0,
    GL_DRAW_FRAMEBUFFER,
    GL_FLOAT,
    GL_GREEN_BIAS,
    GL_GREEN_SCALE,
    GL_LINEAR,
    GL_LUMINANCE,
    GL_MAP_COLOR,
    GL_MODELVIEW,
    GL_NEAREST,
    GL_PROJECTION,
    GL_QUADS,
    GL_RED_BIAS,
    GL_RED_SCALE,
    GL_RGB,
    GL_SHORT,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_UNPACK_ALIGNMENT,
    GL_UNPACK_SWAP_BYTES,
    GL_UNSIGNED_BYTE,
    GL_UNSIGNED_SHORT,
    glBegin,
    glBindFramebuffer,
    glBindTexture,
    glColor3f,
    glDeleteTextures,
    glEnable,
    glEnd,
    glFramebufferTexture2D,
    glGenFramebuffers,
    glGenTextures,
    glLoadIdentity,
    glMatrixMode,
    glOrtho,
    glPixelStorei,
    glPixelTransferf,
    glPixelTransferi,
    glPopMatrix,
    glPushMatrix,
    glTexCoord2f,
    glTexImage2D,
    glTexParameteri,
    glTexSubImage2D,
    glTranslatef,
    glVertex2f,
    glViewport,
)


## This module contains the Tile and MegaTile classes, along with some
# supporting functions and constants.

## Finds the smallest powers of two that will contain a texture with the 
# specified dimensions.
def getTexSize(width, height):
    result = [2, 2]
    for i, val in enumerate([width, height]):
        while result[i] < val:
            result[i] *= 2
    return tuple(result)


## Maps numpy datatypes to OpenGL datatypes
dtypeToGlTypeMap = {
    numpy.uint8: GL_UNSIGNED_BYTE,
    numpy.uint16: GL_UNSIGNED_SHORT,
    numpy.int16: GL_SHORT,
    numpy.float32: GL_FLOAT,
    numpy.float64: GL_FLOAT,
    numpy.int32: GL_FLOAT,
    numpy.uint32: GL_FLOAT,
    numpy.complex64: GL_FLOAT,
    numpy.complex128: GL_FLOAT,
}

## This class handles a single tile in the mosaic.
class Tile:
    def __init__(self, textureData, pos, size,
            histogramScale, layer, shouldDelayAllocation=False):

        ## Array of pixel brightnesses
        self.textureData = textureData
        ## XYZ position tuple, in microns. NB the Z portion is ignored
        # for rendering purposes and is mostly just kept around so we know
        # the Z altitude at which the tile was collected, for later use.
        self.pos = pos
        ## width/height tuple, in microns
        self.size = size
        ## Box describing space we occupy: (upper left corner, lower right corner)
        self.box = (self.pos[:2], (self.pos[0] + self.size[0], self.pos[1] + self.size[1]))

        ## Grouping this tile belongs to, used to toggle display
        self.layer = layer

        ## OpenGL texture ID
        self.texture = glGenTextures(1)
        self.scaleHistogram(histogramScale[0], histogramScale[1])
        # Indicate refresh required after scaling histogram.
        self.shouldRefresh = False
        if not shouldDelayAllocation:
            self.bindTexture()
            self.refresh()


    def bindTexture(self):
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST)
        # These two are only really needed for megatiles; normal
        # tiles don't have to deal with texture wrapping.
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)

        img = self.textureData

        pic_ny, pic_nx = img.shape
        tex_nx,tex_ny = getTexSize(pic_nx,pic_ny)

        imgType = img.dtype.type
        if imgType not in dtypeToGlTypeMap:
            raise ValueError("Unsupported data mode %s" % str(imgType))
        glTexImage2D(GL_TEXTURE_2D,0,  GL_RGB, tex_nx,tex_ny, 0, 
                     GL_LUMINANCE, dtypeToGlTypeMap[imgType], None)


    def refresh(self):
        img = self.textureData
        mi,ma = self.histogramScale
        pic_ny, pic_nx = img.shape
        if img.dtype.type in (numpy.float64, numpy.int32, numpy.uint32):
            data = img.astype(numpy.float32)
            imgString = data.tostring()
            imgType = numpy.float32
        else:
            imgString = img.tostring()
            imgType = img.dtype.type
            
        # maxUShort: value that represents "maximum color" - i.e. white
        if img.dtype.type == numpy.uint16:
            maxUShort = (1<<16) -1
        elif img.dtype.type == numpy.int16:
            maxUShort = (1<<15) -1
        elif img.dtype.type == numpy.uint8:
            maxUShort = (1<<8) -1
        else:
            maxUShort = 1

        mmrange =  float(ma)-float(mi)
        fBias =  -float(mi) / mmrange
        f  =  maxUShort / mmrange
        
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glPixelTransferf(GL_RED_SCALE,   f)
        glPixelTransferf(GL_GREEN_SCALE, f)
        glPixelTransferf(GL_BLUE_SCALE,  f)
        
        glPixelTransferf(GL_RED_BIAS,   fBias)
        glPixelTransferf(GL_GREEN_BIAS, fBias)
        glPixelTransferf(GL_BLUE_BIAS,  fBias)
        
        glPixelTransferi(GL_MAP_COLOR, False)
        
        if img.dtype.type in (numpy.float64, numpy.int32, numpy.uint32,
                numpy.complex64, numpy.complex128):
            itSize = 4
            glPixelStorei(GL_UNPACK_SWAP_BYTES, False) # create native float32 copy - see below
        else:
            itSize = img.itemsize
            glPixelStorei(GL_UNPACK_SWAP_BYTES, not img.dtype.isnative)

        glPixelStorei(GL_UNPACK_ALIGNMENT, itSize)

        if imgType not in dtypeToGlTypeMap:
            raise ValueError("Unsupported data mode %s" % str(imgType))
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, pic_nx, pic_ny,  
                     GL_LUMINANCE, dtypeToGlTypeMap[imgType], imgString)


    ## Free up memory we were using.
    def wipe(self):
        glDeleteTextures([self.texture])


    ## Wipe our texture and recreate it, presumably because it has
    # changed somehow.
    def recreateTexture(self):
        self.wipe()
        self.texture = glGenTextures(1)
        self.bindTexture()


    ## Return true iff our area intersects the given
    # (bottomLeft, topRight) tuple.
    def intersectsBox(self, viewBox):
        bottomLeft, topRight = viewBox
        tileBottomLeft, tileTopRight = self.box

        if (tileBottomLeft[0] > topRight[0] or
                tileTopRight[0] < bottomLeft[0] or
                tileTopRight[1] < bottomLeft[1] or
                tileBottomLeft[1] > topRight[1]):
            return False
        return True


    ## Draw the tile, if it intersects the given view box
    def render(self, viewBox):
        if not self.intersectsBox(viewBox):
            return
        if self.shouldRefresh:
            self.refresh()
            self.shouldRefresh = False
        
        glColor3f(1, 1, 1)

        img = self.textureData
        pic_ny, pic_nx = img.shape
        tex_nx,tex_ny = getTexSize(pic_nx,pic_ny)
        picTexRatio_x = float(pic_nx) / tex_nx
        picTexRatio_y = float(pic_ny) / tex_ny

        (x,y) = self.pos[:2]

        glBindTexture(GL_TEXTURE_2D, self.texture)
        glBegin(GL_QUADS)
        glTexCoord2f(0, picTexRatio_y)
        glVertex2f(x, y)
        glTexCoord2f(picTexRatio_x, picTexRatio_y)
        glVertex2f(x + self.size[0], y)
        glTexCoord2f(picTexRatio_x, 0)
        glVertex2f(x + self.size[0], y + self.size[1])
        glTexCoord2f(0, 0)
        glVertex2f(x, y + self.size[1])
        glEnd()


    ## Set our histogramScale tuple to (min, max), or base those off of 
    # self.textureData if the provided values are None
    def scaleHistogram(self, minVal = None, maxVal = None):
        if minVal is None:
            minVal = self.textureData.min()
        if maxVal is None:
            maxVal = self.textureData.max()
        if minVal == maxVal:
            # Prevent dividing by zero when we have to scale by these
            # values for display.
            maxVal = minVal + 1
        ## Used to scale the brightness of the overall tile, like the
        # histogram controls used for the camera views.
        self.histogramScale = (minVal, maxVal)
        self.shouldRefresh = True


    ## Return the (xSize, ySize) tuple of a single pixel of texture data in GL
    # units.
    def getPixelSize(self):
        return (self.size[0] / self.textureData.shape[0], 
                self.size[1] / self.textureData.shape[1])

## Framebuffer to use when prerendering. Set to None initially since
# we have to wait for OpenGL to get set up in our window before we can
# use it.
megaTileFramebuffer = None

## This class handles pre-rendering of normal-sized Tile instances
# at a reduced level of detail, which allows us to keep the program
# responsive even when thousands of tiles are in view.
class MegaTile(Tile):
    ## Length in pixels of one edge of a MegaTile's texture.
    pixelSize = None
    ## Length in microns of one edge of a MegaTile's texture.
    micronSize = None
    ## An array of ones, used to initialize the MegaTile textures.
    _emptyTileData = None

    ## Instantiate the megatile. The main difference here is that
    # megatiles don't allocated any video memory until they have
    # something to display; since the majority of the mosaic is
    # usually blank, this saves significantly om memory.
    #
    # At this time, if megaTileFramebuffer has not been created
    # yet, create it.
    def __init__(self, pos):
        super().__init__(self._emptyTileData, pos,
                 (self.micronSize, self.micronSize),
                 (0, 1), 'megatiles',
                 shouldDelayAllocation = True)
        ## Counts the number of tiles we've rendered to ourselves.
        self.numRenderedTiles = 0
        ## Whether or not we've allocated memory for our texture yet.
        self.haveAllocatedMemory = False
        
        global megaTileFramebuffer
        if megaTileFramebuffer is None:
            megaTileFramebuffer = glGenFramebuffers(1)

    @classmethod
    def setPixelSize(cls, edge):
        if cls.pixelSize is not None:
            # Class is already initialized - nothing to do.
            # Used to raise an exception here, but both MacroStage and
            # TouchScreen have MacroStageZ instances that each call this
            # method, and raising an exception will prevent correct
            # initialisation of any but the first instance.
            return
        cls.pixelSize = edge
        cls.micronSize = edge * 1
        cls._emptyTileData = numpy.ones( (edge, edge), dtype=numpy.float32)

    ## Go through the provided list of Tiles, find the ones that overlap
    # our area, and prerender them to our texture
    def prerenderTiles(self, tiles):
        if not tiles:
            return
        minX = self.pos[0]
        minY = self.pos[1]
        maxX = self.pos[0] + self.micronSize
        maxY = self.pos[1] + self.micronSize
        viewBox = ((minX, minY), (maxX, maxY))
        newTiles = []
        for tile in tiles:
            if tile.intersectsBox(viewBox):
                newTiles.append(tile)
        if newTiles:
            # Allocate memory for our texture, if needed.
            if not self.haveAllocatedMemory:
                self.bindTexture()
                self.refresh()
                self.haveAllocatedMemory = True
            self.numRenderedTiles += len(newTiles)
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, megaTileFramebuffer)
            glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER,
                    GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D,
                    self.texture, 0)
            
            glPushMatrix()
            glLoadIdentity()
            glViewport(0, 0, self.pixelSize, self.pixelSize)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(0, self.micronSize, self.micronSize, 0, 1, 0)
            glTranslatef(-self.pos[0], -self.pos[1], 0)
            glMatrixMode(GL_MODELVIEW)

            glEnable(GL_TEXTURE_2D)
            for tile in newTiles:
                tile.render(viewBox)

            glPopMatrix()            
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)


    ## Prevent trying to delete our texture if we haven't made it yet.
    def wipe(self):
        if self.haveAllocatedMemory:
            super().wipe()
            self.haveAllocatedMemory = False
            self.numRenderedTiles = 0
            

    ## Prevent allocating a new texture if we haven't drawn anything yet.
    def recreateTexture(self):
        if self.haveAllocatedMemory:
            super().recreateTexture()
            self.refresh()


    def render(self, viewBox):
        if not self.numRenderedTiles:
            # We're empty, so no need to render.
            return
        super().render(viewBox)
