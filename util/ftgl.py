import ctypes
import os

from ctypes import POINTER, c_char_p, c_int, c_uint

if os.name in ('nt', 'ce'):
    _ftgl = ctypes.WinDLL("ftgl")
else:
    _ftgl = ctypes.CDLL("libftgl.so")

class _FTGLfont(ctypes.Structure):
    pass

## macros for rendering modes in FTGL/ftgl.h
_FTGL_RENDER_FRONT = c_int(0x0001)
_FTGL_RENDER_BACK = c_int(0x0002)
_FTGL_RENDER_SIDE = c_int(0x0004)
_FTGL_RENDER_ALL = c_int(0xffff)

## FT_Error is a typedef for a freetype enum.  Typical Freetype builds
## will not include a map for error number to error message.  Instead,
## they provide macros for clients to build the map themselves.  FTGL
## does not use it.  So we will only check if it's different from 0.
## See https://www.freetype.org/freetype2/docs/reference/ft2-error_enumerations.html
_FT_Error = c_int


## FTGLfont* ftglCreateTextureFont (const char* file)
_createTextureFont = _ftgl.ftglCreateTextureFont
_createTextureFont.argtypes = [c_char_p]
_createTextureFont.restype = POINTER(_FTGLfont)

## unsigned int ftglGetFontFaceSize (FTGLfont* font)
_getFontFaceSize = _ftgl.ftglGetFontFaceSize
_getFontFaceSize.argtypes = [POINTER(_FTGLfont)]
_getFontFaceSize.restype = c_uint

## void ftglRenderFont (FTGLfont *font, const char *string, int mode)
_renderFont = _ftgl.ftglRenderFont
_renderFont.argtypes = [POINTER(_FTGLfont), c_char_p, c_int]
_renderFont.restype = None

## int ftglSetFontFaceSize (FTGLfont* font, unsigned int size, unsigned int res)
_setFontFaceSize = _ftgl.ftglSetFontFaceSize
_setFontFaceSize.argtypes = [POINTER(_FTGLfont), c_uint, c_uint]
_setFontFaceSize.restype = c_int

## FT_Error ftglGetFontError (FTGLfont* font)
_getFontError = _ftgl.ftglGetFontError
_getFontError.argtypes = [POINTER(_FTGLfont)]
_getFontError.restype = _FT_Error


class TextureFont(object):
    def __init__(self, path):
        self._font = _createTextureFont(path.encode('ascii'))
        if not self._font:
            raise RuntimeError("failed to create texture font from '%s'" % path)

    def getFaceSize(self):
        return _getFontFaceSize(self._font)

    def setFaceSize(self, size, res=5):
        if _setFontFaceSize(self._font, size, res) != 1:
            raise RuntimeError("failed to set font to size '%i' with res '%i'"
                               % (size, res))

    def render(self, text, mode=_FTGL_RENDER_ALL):
        _renderFont(self._font, text.encode('ascii'), mode)
        err = _getFontError(self._font)
        if err != 0:
            raise RuntimeError("failed to render '%s'", text)
