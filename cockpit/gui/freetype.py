#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

## This file is a Python port of the bits in the FTGL library that we
## care about for cockpit.  FTGL was distributed with the following
## copyright notice:
##
## Copyright (c) 2001-2004 Henry Maddocks <ftgl@opengl.geek.nz>
## Copyright (c) 2008 Sam Hocevar <sam@hocevar.net>
##
## Permission is hereby granted, free of charge, to any person obtaining
## a copy of this software and associated documentation files (the
## "Software"), to deal in the Software without restriction, including
## without limitation the rights to use, copy, modify, merge, publish,
## distribute, sublicense, and/or sell copies of the Software, and to
## permit persons to whom the Software is furnished to do so, subject to
## the following conditions:
##
## The above copyright notice and this permission notice shall be
## included in all copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
## EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
## MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
## IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
## CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
## TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
## SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Wrapper around freetype to write on OpenGL.

This is effectively a port of the bits of FTGL that cockpit uses.  We
did this port, instead of using FTGL, because it's difficult for users
to get FTGL installed (see issue #615).

"""

import freetype
import numpy
import pkg_resources
from OpenGL.GL import (
    GL_ALPHA,
    GL_BLEND,
    GL_CLAMP,
    GL_CLIENT_PIXEL_STORE_BIT,
    GL_COLOR_BUFFER_BIT,
    GL_ENABLE_BIT,
    GL_FALSE,
    GL_LINEAR,
    GL_MODULATE,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_QUADS,
    GL_SRC_ALPHA,
    GL_TEXTURE_2D,
    GL_TEXTURE_BIT,
    GL_TEXTURE_ENV,
    GL_TEXTURE_ENV_MODE,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_UNPACK_ALIGNMENT,
    GL_UNPACK_LSB_FIRST,
    GL_UNPACK_ROW_LENGTH,
    GL_UNSIGNED_BYTE,
    glBegin,
    glBindTexture,
    glBlendFuncSeparate,
    glDeleteTextures,
    glEnable,
    glEnd,
    glGenTextures,
    glPixelStorei,
    glPopAttrib,
    glPopClientAttrib,
    glPushAttrib,
    glPushClientAttrib,
    glTexCoord2f,
    glTexEnvi,
    glTexImage2D,
    glTexParameterf,
    glTexParameteri,
    glVertex2f,
)
import wx


# The resource_name argument for resource_filename is not a filesystem
# filepath.  It is a /-separated filepath, even on windows, so do not
# use os.path.join.
_FONT_PATH = pkg_resources.resource_filename(
    'cockpit',
    'resources/fonts/UniversalisADFStd-Regular.otf'
)


class _Glyph:
    def __init__(self, face: freetype.Face, char: str) -> None:
        if face.load_char(char,freetype.FT_LOAD_RENDER):
            raise RuntimeError('failed to load char \'%s\'' % char)
        glyph = face.glyph
        bitmap = glyph.bitmap

        assert bitmap.pixel_mode == freetype.FT_PIXEL_MODE_GRAY, \
            "We haven't implemented support for other pixel modes"

        glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT)
        glPixelStorei(GL_UNPACK_LSB_FIRST, GL_FALSE)
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        self._texture_id = glGenTextures(1)
        self._width = bitmap.width
        self._height = bitmap.rows

        self._descender = glyph.bitmap_top - self._height
        self._bearing_x = glyph.bitmap_left
        self._advance = numpy.array([face.glyph.advance.x / 64.0,
                                     face.glyph.advance.y / 64.0])

        glBindTexture(GL_TEXTURE_2D, self._texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        data = numpy.array(bitmap.buffer, numpy.ubyte).reshape(self._height,
                                                               self._width)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_ALPHA, self._width, self._height, 0,
                     GL_ALPHA, GL_UNSIGNED_BYTE, numpy.flipud(data))

        glPopClientAttrib()

    def release(self) -> None:
        """Delete associated textures.

        We need to use this instead of ``__del__`` because by the time
        the finaliser is called the GLContext might already have been
        destroyed.

        """
        glDeleteTextures([self._texture_id])

    @property
    def advance(self) -> numpy.ndarray:
        return self._advance

    def render(self, pen: numpy.array) -> None:
        glBindTexture(GL_TEXTURE_2D, self._texture_id)

        left = pen[0] + self._bearing_x
        bottom = pen[1] + self._descender

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(left, bottom)

        glTexCoord2f(1, 0)
        glVertex2f(left + self._width, bottom)

        glTexCoord2f(1, 1)
        glVertex2f(left + self._width, bottom + self._height)

        glTexCoord2f(0, 1)
        glVertex2f(left, bottom + self._height)

        glEnd()


class Face:
    """
    Args:
        window: A wx window whose destruction will trigger the release
            of the resources.  This is required to ensure that it
            happens while the GLContext is still active.
        size:
    """
    def __init__(self, window: wx.Window, size: int) -> None:
        super().__init__()
        self._face = freetype.Face(_FONT_PATH)
        self._face.set_char_size(size*64)
        self._glyphs = {} # type: typing.Dict[str, _Glyph]

        window.Bind(wx.EVT_WINDOW_DESTROY, self._OnWindowDestroy)

    def _OnWindowDestroy(self, event: wx.WindowDestroyEvent) -> None:
        while self._glyphs:
            char_glyph = self._glyphs.popitem()
            char_glyph[1].release()
        event.Skip()

    def render(self, text: str) -> None:
        glPushAttrib(GL_ENABLE_BIT|GL_COLOR_BUFFER_BIT|GL_TEXTURE_BIT)

        glEnable(GL_TEXTURE_2D)
        glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

        glEnable(GL_BLEND)
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
                            GL_ONE, GL_ONE_MINUS_SRC_ALPHA)

        pen = numpy.array([0.0, 0.0])
        for i in range(len(text)):
            char = text[i]
            if char not in self._glyphs:
                self._glyphs[char] = _Glyph(self._face, char)

            self._glyphs[char].render(pen)
            pen += self._glyphs[char].advance

            if i+1 < len(text):
                kerning = self._face.get_kerning(self._face.get_char_index(char),
                                                 self._face.get_char_index(text[i+1]))
                pen += numpy.array([kerning.x/64.0, kerning.y/64.0])

        glPopAttrib()
