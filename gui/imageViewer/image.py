import numpy
import OpenGL.GL as GL
    

## @package gui.image
# This module provides a simple way to draw Numpy arrays with OpenGL.

## Maps numpy datatypes to OpenGL datatypes
dtypeToGlTypeMap = {
    numpy.uint8: GL.GL_UNSIGNED_BYTE,
    numpy.uint16: GL.GL_UNSIGNED_SHORT,
    numpy.int16: GL.GL_SHORT,
    numpy.float32: GL.GL_FLOAT,
    numpy.float64: GL.GL_FLOAT,
    numpy.int32: GL.GL_FLOAT,
    numpy.uint32: GL.GL_FLOAT,
    numpy.complex64: GL.GL_FLOAT,
    numpy.complex128: GL.GL_FLOAT,
}

## Maps numpy datatypes to the maximum value the datatype can represent
dtypeToMaxValMap = {
    numpy.uint16: (1 << 16) - 1,
    numpy.int16: (1 << 15) - 1,
    numpy.uint8: (1 << 8) - 1, 
    numpy.bool_: (1 << 8) - 1,
    numpy.float32: 1
}


## This class handles display of a single 2D array of pixel data.
class Image:
    def __init__(self, imageData):
        self.imageData = imageData
        # Cast to negatable types
        self.imageMin = float(imageData.min())
        self.imageMax = float(imageData.max())
        self.dx = 0
        self.dy = 0
        self.angle = 0
        self.zoom = 1
        self.color = (1, 1, 1)
        self.isVisible = True
        
        self.bindTexture()
        self.refresh()
        

    def bindTexture(self):
        pic_ny, pic_nx = self.imageData.shape

        if self.imageMin == 0 and self.imageMax == 0:
            # Cast to negatable types
            self.imageMin = float(self.imageData.min())
            self.imageMax = float(self.imageData.max())

        # Generate texture sizes that are powers of 2
        tex_nx = 2
        while tex_nx < pic_nx:
            tex_nx *= 2
        tex_ny = 2
        while tex_ny < pic_ny:
            tex_ny *= 2

        self.picTexRatio_x = float(pic_nx) / tex_nx
        self.picTexRatio_y = float(pic_ny) / tex_ny

        self.textureID = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textureID)

        # Define this new texture object based on self.imageData's geometry
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER,
                GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER,
                GL.GL_NEAREST)

        imgType = self.imageData.dtype.type
        if imgType not in dtypeToGlTypeMap:
            raise ValueError, "Unsupported data mode %s" % str(imgType)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,  GL.GL_LUMINANCE16, tex_nx,tex_ny, 0,
                     GL.GL_LUMINANCE, dtypeToGlTypeMap[imgType], None)


    def refresh(self):
        minMaxRange = float(self.imageMax - self.imageMin)
        if abs(self.imageMax - self.imageMin) < 1:
            minMaxRange = 1
        
        imgType = self.imageData.dtype.type
        fBias = -self.imageMin / minMaxRange
        f = dtypeToMaxValMap[imgType] / minMaxRange

        if self.textureID is None:
            raise Exception('Texture was deleted and not rebound.')

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textureID)

        # Texture validation - should not be necessary. It only seems to be
        # texture 1 that needs recreating when the camera view tiles are
        # rearranged.
        textureWidth = GL.glGetTexLevelParameteriv(GL.GL_TEXTURE_2D, 0, GL.GL_TEXTURE_WIDTH)
        textureHeight = GL.glGetTexLevelParameteriv(GL.GL_TEXTURE_2D, 0, GL.GL_TEXTURE_HEIGHT)
        if (textureWidth == 0) or (textureHeight == 0):
            # Something happend to our texture. Delete and regenerate it.
            self.wipe()
            self.bindTexture()
            print ("Recreated texture %s." % self.textureID)

        GL.glPixelTransferf(GL.GL_RED_SCALE,   f)
        GL.glPixelTransferf(GL.GL_GREEN_SCALE, f)
        GL.glPixelTransferf(GL.GL_BLUE_SCALE,  f)

        GL.glPixelTransferf(GL.GL_RED_BIAS,   fBias)
        GL.glPixelTransferf(GL.GL_GREEN_BIAS, fBias)
        GL.glPixelTransferf(GL.GL_BLUE_BIAS,  fBias)

        GL.glPixelTransferf(GL.GL_MAP_COLOR, False)

        GL.glPixelStorei(GL.GL_UNPACK_SWAP_BYTES,
                not self.imageData.dtype.isnative)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, self.imageData.itemsize)
        
        imgString = self.imageData.tostring()

        pic_ny, pic_nx = self.imageData.shape

        if imgType not in dtypeToGlTypeMap:
            raise ValueError, "Unsupported data mode %s" % str(imgType)

        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, pic_nx, pic_ny,
                GL.GL_LUMINANCE, dtypeToGlTypeMap[imgType], imgString)


    def render(self):
        cx,cy = self.imageData.shape[-1]/2., self.imageData.shape[-2]/2.
        GL.glPushMatrix()

        # To rotate about the center, first we have to move to it.
        GL.glTranslated(self.dx + cx, self.dy + cy, 0)
        
        GL.glScaled(self.zoom, self.zoom, 1)

        GL.glRotated(-self.angle, 0, 0, 1)
        GL.glTranslated(-cx, -cy, 0)

        GL.glColor3fv(self.color)

        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textureID)

        GL.glBegin(GL.GL_QUADS)
       
        pic_ny, pic_nx = self.imageData.shape

        ###//(0,0) at left bottom
        GL.glTexCoord2f(0, 0)
        GL.glVertex2i(0, 0)
            
        GL.glTexCoord2f(self.picTexRatio_x, 0)
        GL.glVertex2i(pic_nx, 0)
            
        GL.glTexCoord2f(self.picTexRatio_x, self.picTexRatio_y)
        GL.glVertex2i(pic_nx, pic_ny)
            
        GL.glTexCoord2f(0, self.picTexRatio_y)
        GL.glVertex2i(0, pic_ny)

        GL.glEnd()
        GL.glPopMatrix()


    ## Free the allocated GL texture
    def wipe(self):
        GL.glDeleteTextures(self.textureID)
        self.textureID = None
   

    ## Accept a new array of image data.
    def updateImage(self, imageData):
        self.imageData = imageData

        self.refresh()


    def setMinMax(self, imageMin, imageMax):
        # Ensure these are negatable types, for our refresh
        # method. Otherwise we run into trouble when
        # we negate self.imageMin. 
        self.imageMin = float(imageMin)
        self.imageMax = float(imageMax)


    def setTransform(self, dx, dy, angle, zoom):
        self.dx = dx
        self.dy = dy
        self.angle = angle
        self.zoom = zoom


    def setColor(self, color):
        self.color = color


    def toggleVisibility(self):
        self.isVisible = not self.isVisible

