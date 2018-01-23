import ctypes
from ctypes import WINFUNCTYPE, WinDLL, c_void_p, c_uint, c_int, c_char_p

_lib = WinDLL("ftgl")
#prototype = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
#f = prototype(getattr(lib, "??0FTTextureFont@@QEAA@PEBD@Z"))
#TextureFont = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)(getattr(lib, "??0FTTextureFont@@QEAA@PEBD@Z"))
#setFontFaceSize = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_long_p, ctypes.c_int)(getattr(lib, "??0FTTextureFont@@QEAA@PEBD@Z"))

# FTGLfont *ftglCreateTextureFont(const char *file);
pr = WINFUNCTYPE(c_void_p, c_char_p)
pf = ((1, "filename"),)
_createTextureFont = pr(('ftglCreateTextureFont', _lib), pf)

#setFontFaceSize = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int)(lib.ftglSetFontFaceSize)

# uint ftglGetFontFaceSize (FTGLfont *font) 
# Get the current face size in points (1/72 inch). 
pr = WINFUNCTYPE(c_uint, c_void_p)
pf = ((1, "FTGLfont"),)
_getFontFaceSize = pr(('ftglGetFontFaceSize', _lib), pf)

# int ftglSetFontFaceSize (FTGLfont *font, unsigned int size, unsigned int res)
# Set the char size for the current face. 
pr = WINFUNCTYPE(c_int, c_void_p, c_uint, c_uint)
pf = ((1, "FTGLfont"), (1, "size"), (5, "res"))
_setFontFaceSize = pr(('ftglSetFontFaceSize', _lib), pf)

# void ftglRenderFont (FTGLfont *font, const char *string, int mode)
# Render a string of characters. 
# enum    RenderMode { RENDER_FRONT = 0x0001, RENDER_BACK = 0x0002, RENDER_SIDE = 0x0004, RENDER_ALL = 0xffff }
pr = WINFUNCTYPE(c_void_p, c_void_p, c_char_p, c_int)
pf = ((1, "FTGLfont"), (1, "text"), (1, "mode"))
_renderFont = pr(('ftglRenderFont', _lib), pf)


class TextureFont(object):
    def __init__(self, path):
        self._font = _createTextureFont(path.encode('ascii'))

    def getFaceSize(self):
        return _getFontFaceSize(self._font)

    def setFaceSize(self, size):
        return _setFontFaceSize(self._font, size)

    def render(self, text):
        return _renderFont(self._font, text.encode('ascii'), 0xffff)