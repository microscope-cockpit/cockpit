#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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


## This module exists to make interacting with MRC files more pleasant from a
# programming perspective. I (Chris Weisiger) originally wrote it for the OMX
# Editor program, since I needed to be able to construct multiple views and
# transformations of data on the fly. It's since expanded to provide multiple
# utility functions for reading and writing MRC files and headers.

from cockpit.util import Mrc

import numpy
import scipy.ndimage
import wx


## Maps dimensional axes to their labels.
DIMENSION_LABELS = ['Wavelength', 'Time', 'Z', 'Y', 'X']



## The DataDoc class is, broadly, a wrapper around the Mrc module. When it
# loads a file, it loads all of the data in that file, and then makes it
# available as an array in WTZYX order (regardless of the order in which the
# data is stored in the MRC file). It additionally exposes some attributes of
# the MRC metadata, and provides functions for transforming and projecting
# the data array.
class DataDoc:
    ## Instantiate the object.
    # \param filename The filename of the MRC file you want to load.
    def __init__(self, filename = ''):
        ## Loaded MRC object. Note this is not just an array of pixels.
        self.image = Mrc.bindFile(filename)
        ## Header for the image data, which tells us e.g. what the ordering
        # of X/Y/Z/time/wavelength is in the MRC file.
        self.imageHeader = Mrc.implement_hdr(self.image.Mrc.hdr._array.copy())
        ## Location the file is saved on disk.
        self.filePath = self.image.Mrc.path

        ## Number of wavelengths in the array.
        self.numWavelengths = self.imageHeader.NumWaves
        numTimepoints = self.imageHeader.NumTimes
        numX = self.imageHeader.Num[0]
        numY = self.imageHeader.Num[1]
        numZ = self.imageHeader.Num[2] // (self.numWavelengths * numTimepoints)
        ## Size in pixels of the data, since having it as a Numpy array
        # instead of a tuple (from self.imageArray.shape) is occasionally
        # handy.
        self.size = numpy.array([self.numWavelengths, numTimepoints, numZ, numY, numX], dtype = numpy.int)
        ## 5D array of pixel data, indexed as
        # self.imageArray[wavelength][time][z][y][x]
        # In other words, in WTZYX order. In general we try to treat
        # Z and time as "just another axis", but wavelength is dealt with
        # specially.
        self.imageArray = self.getImageArray()
        ## Two arrays, one for ints, one for floats, for the extended header.
        # Indexed as
        # self.extendedHeaderInts[wavelength, time, z, i]
        # Either may be empty, depending on how big the extended header is.
        self.extendedHeaderInts, self.extendedHeaderFloats = getExtendedHeader(
                self.image.Mrc.e, self.imageHeader)
        ## Datatype of our array.
        self.dtype = self.imageArray.dtype.type

        ## Averages for each wavelength, used to provide fill values when
        # taking slices.
        self.averages = []
        for wavelength in range(self.numWavelengths):
            self.averages.append(self.imageArray[wavelength].mean())

        ## Lower boundary of the cropped data.
        self.cropMin = numpy.array([0, 0, 0, 0, 0], numpy.int32)
        ## Upper boundary of the cropped data.
        self.cropMax = numpy.array(self.size, numpy.int32)

        ## Index of the single pixel that is visible in all different data
        # views.
        self.curViewIndex = numpy.array(self.size / 2, numpy.int)
        # Initial time view is at 0
        self.curViewIndex[1] = 0

        ## Parameters for transforming different wavelengths so they align
        # with each other. Order is dx, dy, dz, angle, zoom
        self.alignParams = numpy.zeros((self.size[0], 5), numpy.float32)
        # Default zoom to 1.0
        self.alignParams[:,4] = 1.0

        ## List of functions to call whenever the alignment parameters change.
        # Each will be passed self.alignParams so it can take whatever
        # action is necessary.
        self.alignCallbacks = []

    def getNPlanes(self):
        return numpy.prod(self.size[0:3])

    ## Convert the loaded MRC image data into a 5D array of pixel data in
    # WTZYX order.
    def getImageArray(self):
        # This is a string describing the dimension ordering as stored in
        # the file.
        return reorderArray(self.image, self.size, self.image.Mrc.axisOrderStr())


    ## Passthrough to takeSliceFromData, using our normal array.
    def takeSlice(self, axes, shouldTransform = True, order = 1):
        return self.takeSliceFromData(self.imageArray, axes, shouldTransform, order)


    ## As takeSlice, but do a max-intensity projection across one axis. This
    # becomes impossible to do efficiently if we have rotation or scaling in
    # a given wavelength, so we just have to transform the entire volume. It
    # gets *really* expensive if we want to do projections across time with
    # this...
    # \todo We could be a bit more efficient here since only the wavelengths
    # with nonzero rotation/scaling need to be transformed as volumes.
    def takeProjectedSlice(self, axes, projectionAxis, shouldTransform,
            order = 1):
        if (projectionAxis == 2 or
                (numpy.all(self.alignParams[:,3] == 0) and
                 numpy.all(self.alignParams[:,4] == 1))):
            # Scaling/rotation doesn't affect the projection; lucky us!
            data = self.imageArray.max(axis = projectionAxis)
            # Augment data with an extra dimension to replace the one we
            # flattened out.
            data = numpy.expand_dims(data, projectionAxis)
            # Since we flattened out this axis, change its index to be the only
            # possible valid index.
            axes[projectionAxis] = 0
            return self.takeSliceFromData(data, axes, shouldTransform, order)
        elif projectionAxis in [3, 4]:
            # Projecting through Y or X; just transform the local volume.
            dialog = wx.ProgressDialog(
                    title = "Constructing projection",
                    message = "Please wait...",
                    maximum = self.size[0],
                    style = wx.PD_AUTO_HIDE | wx.PD_REMAINING_TIME)
            curTimepoint = self.curViewIndex[1]
            data = []
            for wavelength in range(self.size[0]):
                data.append(self.transformArray(
                        self.imageArray[wavelength, curTimepoint],
                        *self.alignParams[wavelength],
                        order = 1))
                dialog.Update(wavelength)
            data = numpy.array(data, dtype = self.dtype)
            dialog.Destroy()
            return data.max(axis = projectionAxis - 1)
        else:
            # Projecting through time; transform EVERY volume. Ouch.
            dialog = wx.ProgressDialog(
                    title = "Constructing projection",
                    message = "Please wait...",
                    maximum = self.size[0] * self.size[1],
                    style = wx.PD_AUTO_HIDE | wx.PD_REMAINING_TIME)
            data = []
            for timepoint in range(self.size[1]):
                timeData = []
                for wavelength in range(self.size[0]):
                    volume = self.transformArray(
                            self.imageArray[wavelength, timepoint],
                            *self.alignParams[wavelength],
                            order = 1)
                    timeData.append(volume)
                    dialog.Update(timepoint * self.size[0] + wavelength)
                timeData = numpy.array(timeData, dtype = self.dtype)
                data.append(timeData)

            data = numpy.array(data, dtype = self.dtype)
            data = data.max(axis = 0)
            dialog.Destroy()
            # Slice through data per our axes parameter.
            slice = [Ellipsis] * 4
            for axis, position in axes.items():
                if axis != 1:
                    slice[axis - 1] = position
                    return data[slice]
            raise RuntimeError("Couldn't find a valid slice axis.")


    ## Generate a 2D slice of the given data in each wavelength. Since the
    # data is 5D (wavelength/time/Z/Y/X), there are three axes to be
    # perpendicular to, one of which is always wavelength. The "axes"
    # argument maps the other two axis indices to the coordinate the slice
    # should pass through.
    # E.g. passing in {1: 10, 2: 32} means to take a WXY slice at timepoint
    # 10 through Z index 32.
    # This was fairly complicated for me to figure out, since I'm not a
    # scientific programmer, so I'm including my general process here:
    # - Figure out which axes the slice cuts across, and generate an array
    #   of the appropriate shape to hold the results.
    # - Create an array of similar size augmented with a length-4 dimension.
    #   This array holds XYZ coordinates for each pixel in the slice; the 4th
    #   index holds a 1 (so that we can use a 4x4 affine transformation matrix
    #   to do rotation and offsets in the same pass). For example, an XY slice
    #   at Z = 5 would look something like this:
    # [  [0, 0, 5]  [0, 1, 5]  [0, 2, 5] ...
    # [  [1, 0, 5]  ...
    # [  [2, 0, 5]
    # [  ...
    # [
    # - Subtract the XYZ center off of the coordinates so that when we apply
    #   the rotation transformation, it's done about the center of the dataset
    #   instead of the corner.
    # - Multiply the inverse transformation matrix by the coordinates.
    # - Add the center back on.
    # - Chop off the dummy 1 coordinate, reorder to ZYX, and prepend the time
    #   dimension.
    # - Pass the list of coordinates off to numpy.map_coordinates so it can
    #   look up actual pixel values.
    # - Reshape the resulting array to match the slice shape.
    def takeSliceFromData(self, data, axes, shouldTransform = True, order = 1):
        if shouldTransform:
            targetShape = []
            targetAxes = []
            presets = [-1] * 5
            # Generate an array to hold the slice. Note this includes all
            # wavelengths.
            for i, size in enumerate(data.shape):
                if i not in axes:
                    targetShape.append(size)
                    targetAxes.append(i)
                else:
                    presets[i] = axes[i]

            # Create a matrix of size (NxMx3) where N and M are the width
            # and height of the desired slice, and the remaining dimension
            # holds the desired XYZ coordinates for each pixel in the slice,
            # pre-transform. Note this is wavelength-agnostic.
            targetCoords = numpy.empty(targetShape[1:] + [3])
            haveAlreadyResized = False
            # Axes here are in WTZYX order, so we need to reorder them to XYZ.
            for axis in [2, 3, 4]:
                if axis in targetAxes:
                    basis = numpy.arange(data.shape[axis])
                    if (data.shape[axis] == targetCoords.shape[0] and
                            not haveAlreadyResized):
                        # Reshape into a column vector. We only want to do this
                        # once, but unfortunately can't tell solely with the
                        # length of the array in the given axis since it's not
                        # uncommon for e.g. X and Y to have the same size.
                        basis.shape = data.shape[axis], 1
                        haveAlreadyResized = True
                    targetCoords[:,:,4 - axis] = basis
                else:
                    targetCoords[:,:,4 - axis] = axes[axis]
            return self.mapCoords(data, targetCoords, targetShape, axes, order)
        else:
            # Simply take an ordinary slice.
            # Ellipsis is a builtin keyword for the full-array slice. Who knew?
            slices = [Ellipsis]
            for axis in range(1, 5):
                if axis in axes:
                    slices.append(axes[axis])
                else:
                    slices.append(Ellipsis)
            return data[slices]


    ## Inverse-transform the provided coordinates and use them to look up into
    # the given array, to generate a transformed slice of the specified shape
    # along the specified axes.
    # \param data A 5D array of pixel data (WTZYX)
    # \param targetCoords 4D array of WXYZ coordinates.
    # \param targetShape Shape of the resulting slice.
    # \param axes Axes the slice cuts along.
    # \param order Spline order to use when mapping. Lower is faster but
    #        less accurate
    def mapCoords(self, data, targetCoords, targetShape, axes, order):
        # Reshape into a 2D list of the desired coordinates
        targetCoords.shape = numpy.product(targetShape[1:]), 3
        # Insert a dummy 4th dimension so we can use translation in an
        # affine transformation.
        tmp = numpy.empty((targetCoords.shape[0], 4))
        tmp[:,:3] = targetCoords
        tmp[:,3] = 1
        targetCoords = tmp

        transforms = self.getTransformationMatrices()
        inverseTransforms = [numpy.linalg.inv(matrix) for matrix in transforms]
        transposedCoords = targetCoords.T
        # XYZ center, which needs to be added and subtracted from the
        # coordinates before/after transforming so that rotation is done
        # about the center of the image.
        center = numpy.array(data.shape[2:][::-1]).reshape(3, 1) / 2.0
        transposedCoords[:3,:] -= center
        result = numpy.zeros(targetShape, dtype = self.dtype)
        for wavelength in range(data.shape[0]):
            # Transform the coordinates according to the alignment
            # parameters for the specific wavelength.
            transformedCoords = numpy.dot(inverseTransforms[wavelength],
                    transposedCoords)
            transformedCoords[:3,:] += center

            # Chop off the trailing 1, reorder to ZYX, and insert the time
            # coordinate.
            tmp = numpy.zeros((4, transformedCoords.shape[1]), dtype = numpy.float)
            for i in range(3):
                tmp[i + 1] = transformedCoords[2 - i]

            transformedCoords = tmp
            if 1 not in axes:
                # User wants a cut across time.
                transformedCoords[0,:] = numpy.arange(data.shape[1]).repeat(
                        transformedCoords.shape[1] / data.shape[1])
            else:
                transformedCoords[0,:] = axes[1]

            resultVals = scipy.ndimage.map_coordinates(
                    data[wavelength], transformedCoords,
                    order = order, cval = self.averages[wavelength])
            resultVals.shape = targetShape[1:]
            result[wavelength] = resultVals

        return result


    ## Return the value for each wavelength at the specified TZYX coordinate,
    # taking transforms into account. Also return the transformed coordinates.
    # \todo This copies a fair amount of logic from self.mapCoords.
    def getValuesAt(self, coord):
        transforms = self.getTransformationMatrices()
        inverseTransforms = [numpy.linalg.inv(matrix) for matrix in transforms]
        # Reorder to XYZ and add a dummy 4th dimension.
        transposedCoord = numpy.array([[coord[3]], [coord[2]],
            [coord[1]], [1]])
        # XYZ center, which needs to be added and subtracted from the
        # coordinates before/after transforming so that rotation is done
        # about the center of the image.
        center = (self.size[2:][::-1] / 2.0).reshape(3, 1)
        transposedCoord[:3] -= center
        resultVals = numpy.zeros(self.numWavelengths, dtype = self.dtype)
        resultCoords = numpy.zeros((self.numWavelengths, 4))
        for wavelength in range(self.numWavelengths):
            # Transform the coordinates according to the alignment
            # parameters for the specific wavelength.
            transformedCoord = numpy.dot(inverseTransforms[wavelength],
                    transposedCoord)
            transformedCoord[:3,:] += center
            # Reorder to ZYX and insert the time dimension.
            transformedCoord = numpy.array([coord[0],
                    transformedCoord[2], transformedCoord[1],
                    transformedCoord[0]],
                dtype = numpy.int
            )
            resultCoords[wavelength,:] = transformedCoord
            transformedCoord.shape = 4, 1

            resultVals[wavelength] = scipy.ndimage.map_coordinates(
                    self.imageArray[wavelength], transformedCoord,
                    order = 1, cval = self.averages[wavelength])[0]
        return resultVals, resultCoords


    ## Take a default slice through our view indices perpendicular to the
    # given axes.
    def takeDefaultSlice(self, perpendicularAxes, shouldTransform = True):
        targetCoords = self.getSliceCoords(perpendicularAxes)
        return self.takeSlice(targetCoords, shouldTransform)


    ## Generate a 4D transformation matrix based on self.alignParams for
    # each wavelength.
    def getTransformationMatrices(self):
        result = []
        for wavelength in range(self.numWavelengths):
            dx, dy, dz, angle, zoom = self.alignParams[wavelength]
            angle = angle * numpy.pi / 180.0
            cosTheta = numpy.cos(angle)
            sinTheta = numpy.sin(angle)
            transform = zoom * numpy.array(
                    [[cosTheta, sinTheta, 0, dx],
                     [-sinTheta, cosTheta, 0, dy],
                     [0, 0, 1, dz],
                     [0, 0, 0, 1]])
            result.append(transform)
        return result


    ## Return true if there is any Z motion in any wavelength's alignment
    # parameters.
    def hasZMotion(self):
        return numpy.any(self.alignParams[:,2] != 0)


    ## Return true if there is any non-default transformation.
    def hasTransformation(self):
        for i, nullValue in enumerate([0, 0, 0, 0, 1]):
            if not numpy.all(self.alignParams[:,i] == nullValue):
                # At least one wavelength has a transformation here.
                return True
        return False


    ## Register a callback to be invoked when the alignment parameters change.
    def registerAlignmentCallback(self, callback):
        self.alignCallbacks.append(callback)


    ## Update the alignment parameters, then invoke our callbacks.
    def setAlignParams(self, wavelength, params):
        self.alignParams[wavelength] = params
        for callback in self.alignCallbacks:
            callback(self.alignParams)


    ## Get the current alignment parameters for the specified wavelength.
    def getAlignParams(self, wavelength):
        return self.alignParams[wavelength]


    ## Apply our alignment parameters to the data, then crop them, and either
    # return the result for the specified wavelength(s), or save the result
    # to the specified file path. If no wavelengths are specified, use them all.
    # \todo All of the logic dealing with the MRC file writing is basically
    # copied from the old imdoc module, and I don't claim to understand why it
    # does what it does.
    # \todo The extended header is not preserved. On the flip side, according
    # to Eric we don't currently use the extended header anyway, so it was
    # just wasting space.
    def alignAndCrop(self, wavelengths = [], timepoints = [],
            savePath = None):
        if not wavelengths:
            wavelengths = range(self.size[0])
        if not timepoints:
            timepoints = range(self.cropMin[1], self.cropMax[1])

        # Generate the cropped shape of the file.
        croppedShape = [len(wavelengths)]
        for min, max in zip(self.cropMin[1:], self.cropMax[1:]):
            croppedShape.append(max - min)
        # Reorder to time/wavelength/z/y/x for saving.
        croppedShape[0], croppedShape[1] = croppedShape[1], croppedShape[0]
        croppedShape = tuple(croppedShape)

        newHeader = Mrc.makeHdrArray()
        Mrc.initHdrArrayFrom(newHeader, self.imageHeader)
        newHeader.Num = (croppedShape[4], croppedShape[3],
                croppedShape[2] * len(timepoints) * len(wavelengths))
        newHeader.NumTimes = len(timepoints)
        newHeader.NumWaves = len(wavelengths)
        # Size of the extended header -- forced to zero for now.
        newHeader.next = 0
        # Ordering of data in the file; 2 means z/w/t
        newHeader.ImgSequence = 2
        newHeader.PixelType = Mrc.dtype2MrcMode(numpy.float32)

        if not savePath:
            outputArray = numpy.empty(croppedShape, numpy.float32)
        else:
            if self.filePath == savePath:
                # \todo Why do we do this?
                del self.image.Mrc

            # Write out the header.
            outputFile = file(savePath, 'wb')
            outputFile.write(newHeader._array.tostring())

        # Slices to use to crop out the 3D volume we want to use for each
        # wave-timepoint pair.
        volumeSlices = []
        for min, max in zip(self.cropMin[2:], self.cropMax[2:]):
            volumeSlices.append(slice(min, max))

        for timepoint in timepoints:
            for waveIndex, wavelength in enumerate(wavelengths):
                volume = self.imageArray[wavelength][timepoint]

                dx, dy, dz, angle, zoom = self.alignParams[wavelength]
                if dz and self.size[2] == 1:
                    # HACK: no Z translate in 2D files. Even
                    # infinitesimal translates will zero out the entire slice,
                    # otherwise.
                    dz = 0
                if dx or dy or dz or angle or zoom != 1:
                    # Transform the volume.
                    volume = self.transformArray(
                            volume, dx, dy, dz, angle, zoom
                    )
                # Crop to the desired shape.
                volume = volume[volumeSlices].astype(numpy.float32)

                if not savePath:
                    outputArray[timepoint, waveIndex] = volume
                else:
                    # Write to the file.
                    for i, zSlice in enumerate(volume):
                        outputFile.write(zSlice)

        if not savePath:
            # Reorder to WTZYX since that's what the user expects.
            return outputArray.transpose([1, 0, 2, 3, 4])
        else:
            outputFile.close()


    ## Just save our array to the specified file.
    def saveTo(self, savePath):
        filehandle = open(savePath, 'wb')
        writeMrcHeader(self.imageHeader, filehandle)
        filehandle.write(self.imageArray)
        filehandle.close()


    ## Get the size of a slice in the specified dimensions. Dimensions are as
    # ordered in self.size
    def getSliceSize(self, axis1, axis2):
        return numpy.array([self.size[axis1], self.size[axis2]])


    ## Returns a mapping of axes to our view positions on those axes.
    # \param axes A list of axes, e.g. [0, 3] for (time, Y). If None, then
    #        operate on all axes.
    def getSliceCoords(self, axes = None):
        if axes is None:
            axes = range(5)
        return dict([(axis, self.curViewIndex[axis]) for axis in axes])


    ## Move self.curViewIndex by the specified amount, ensuring that we stay
    # in-bounds.
    def moveSliceLines(self, offset):
        for i, delta in enumerate(offset):
            targetVal = self.curViewIndex[i] + delta
            if targetVal >= 0 and targetVal < self.size[i]:
                self.curViewIndex[i] = targetVal


    ## Move the crop box by the specified amount, ensuring that we stay
    # in-bounds.
    def moveCropbox(self, offset, isMin):
        if isMin:
            self.cropMin += offset
            for i, val in enumerate(self.cropMin):
                self.cropMin[i] = max(0, min(self.size[i], val))
        else:
            self.cropMax += offset
            for i, val in enumerate(self.cropMax):
                self.cropMax[i] = max(0, min(self.size[i], val))


    ## Multiply the given XYZ offsets by our pixel sizes to get offsets
    # in microns.
    def convertToMicrons(self, offsets):
        return numpy.multiply(offsets, self.imageHeader.d)


    ## As convertToMicrons, but in reverse.
    def convertFromMicrons(self, offsets):
        return numpy.divide(offsets, self.imageHeader.d)


    ## Apply a transformation to an input 3D array in ZYX order. Angle rotates
    # each slice, zoom scales each slice (i.e. neither is 3D).
    def transformArray(self, data, dx, dy, dz, angle, zoom, order = 3):
        # Input angle is in degrees, but scipy's transformations expect angles
        # in radians.
        angle = angle * numpy.pi / 180
        cosTheta = numpy.cos(-angle)
        sinTheta = numpy.sin(-angle)
        affineTransform = zoom * numpy.array(
                [[cosTheta, sinTheta], [-sinTheta, cosTheta]])

        invertedTransform = numpy.linalg.inv(affineTransform)
        yxCenter = numpy.array(data.shape[1:]) / 2.0
        offset = -numpy.dot(invertedTransform, yxCenter) + yxCenter

        output = numpy.zeros(data.shape)
        for i, slice in enumerate(data):
            output[i] = scipy.ndimage.affine_transform(slice, invertedTransform,
                    offset, output = numpy.float32, cval = slice.min(),
                    order = order)
        output = scipy.ndimage.interpolation.shift(output, [dz, dy, dx],
                order = order)
        return output



## Generate an MRC header object based on the provided Numpy array.
# The input array must be five-dimensional, in WTZYX order.
# Just a passthrough to makeHeaderForShape, really.
# \param data Array of pixels in (W, T, Z, Y, X) order.
# \param shouldSetMinMax If True (the default), calculate the min and max
#        values for each wavelength and put them in the header. Pointless if
#        this will be overridden later, and may be costly depending on the
#        size of the data array.
def makeHeaderFor(data, shouldSetMinMax = True, **kwargs):
    header = makeHeaderForShape(data.shape, data.dtype.type, **kwargs)
    if shouldSetMinMax:
        # Set the min/max values. This is a bit ugly because they're in
        # differently-named fields on a per-wavelength basis...and the first
        # wavelength gets extra data stored, to boot.
        for i in range(data.shape[0]):
            minVal = data[i].min()
            maxVal = data[i].max()
            if i == 0:
                setattr(header, 'mmm1', (minVal, maxVal, numpy.median(data[i])))
            else:
                setattr(header, 'mm%d' % (i + 1), (minVal, maxVal))
    return header


## Generate an MRC header, filling in some values.
# \param shape 5D tuple describing the shape of the data. Must be in
#        (W, T, Z, Y, X) order.
# \param dtype Datatype of the pixel data.
# \param XYSize Size of the (assumed square) pixels. Defaults to our current
#        camera pixel size.
# \param ZSize Size of the Z-step between slices. Defaults to 0.
# \param wavelengths List of wavelengths (e.g. [488, 560]). Defaults to
#        the currently active wavelengths.
def makeHeaderForShape(shape, dtype, XYSize = None, ZSize = None,
        wavelengths = []):
    header = Mrc.makeHdrArray()
    Mrc.init_simple(header, Mrc.dtype2MrcMode(dtype),
            shape)
    header.NumTimes = shape[1]
    header.NumWaves = shape[0]
    header.Num = (shape[4], shape[3], shape[0] * shape[1] * shape[2])
    for i, wavelength in enumerate(wavelengths):
        if wavelength:
            header.wave[i] = wavelength
        else:
            header.wave[i] = 0
    header.ImgSequence = 2
    header.d = [XYSize, XYSize, ZSize]
    return header


## Write just a header to the provided filehandle.
def writeMrcHeader(header, filehandle):
    filehandle.seek(0)
    filehandle.write(header._array.tostring())


## Write out the provided data array as if it were an MRC file. Note that
# the input array must be in WTZYX order; if the array has insufficient
# dimensions it will be augmented with dimensions of size 1 starting from
# the left (e.g. a 512x512 array becomes a 1x1x1x512x512 array).
def writeDataAsMrc(data, filename, XYSize = None, ZSize = None, wavelengths = []):
    shape = (5 - len(data.shape)) * [1] + list(data.shape)
    data_out = data.reshape(shape)
    header = makeHeaderFor(data_out, XYSize = XYSize, ZSize = ZSize,
            wavelengths = wavelengths)
    handle = open(filename, 'wb')
    writeMrcHeader(header, handle)
    handle.seek(1024) # Seek to end of header
    data_out.tofile(handle)
    handle.close()


## Given a buffer of memory that contains the extended header, and the
# standard header, return the
# extended header as two arrays: one of the ints, the other of the floats.
def getExtendedHeader(data, header):
    numWavelengths = header.NumWaves
    # \todo Assuming the 'Num' array is in XYZ order.
    imagesPerWavelength = header.Num[2] // numWavelengths
    numInts = header.NumIntegers
    numFloats = header.NumFloats
    # Start with blank bytes; we'll type-convert later.
    intArray = numpy.zeros(int(imagesPerWavelength * numWavelengths * numInts * 4),
            dtype = numpy.uint8)
    floatArray = numpy.zeros(int(imagesPerWavelength * numWavelengths * numFloats * 4),
            dtype = numpy.uint8)
    # Amount of memory per image allocated to ints.
    intSize = int(numInts * 4)
    # Ditto, for floats.
    floatSize = int(numFloats * 4)
    chunkSize = intSize + floatSize
    # Load the extended header as a bytesequence.
    for i in range(imagesPerWavelength * numWavelengths):
        offset = int(i * chunkSize)
        intArray[i * intSize : (i + 1) * intSize] = data[offset : offset + intSize]
        floatArray[i * floatSize : (i + 1) * floatSize] = data[offset + intSize : offset + chunkSize]
    # Cast to appropriate datatypes.
    intArray.dtype = numpy.int32
    floatArray.dtype = numpy.float32

    # Set the array dimensions as if the arrays were of image data.
    # Use the X axis to store the ints/floats (the Y axis is unused).
    orderStr = Mrc.axisOrderStr(header)
    shape = []
    numTimepoints = header.NumTimes
    numZ = header.Num[2] // (numWavelengths * numTimepoints)
    keyToSize = {
            'w': numWavelengths,
            't': numTimepoints,
            'z': numZ,
            'y': 1
    }
    for key in orderStr:
        if key in keyToSize:
            shape.append(keyToSize[key])
    intArray.shape = tuple(shape + [numInts])
    floatArray.shape = tuple(shape + [numFloats])
    # Reorder the arrays to WTZYX order.
    if numInts:
        intArray = reorderArray(intArray,
                (numWavelengths, numTimepoints, numZ, 1, numInts),
                orderStr)
    if numFloats:
        floatArray = reorderArray(floatArray,
                (numWavelengths, numTimepoints, numZ, 1, numFloats),
                orderStr)
    return intArray, floatArray


## Load just the header and extended header for the specified filepath.
def loadHeader(path):
    data = numpy.memmap(path)
    headerBuffer = data[:1024]
    header = Mrc.makeHdrArray(headerBuffer)
    numBytes = header.next
    extendedData = data[1024:1024 + numBytes]
    ints, floats = getExtendedHeader(extendedData, header)
    return header, headerBuffer, ints, floats


## Given an input array, an expected final array shape, and a sequence
# string (e.g. as generated by Mrc.axisOrderStr()), reorder the
# array to be in WTZYX order, with any neccesary padding of the
# array elements.
# How we
# do this depends on the ordering of X/Y/Z/time/wavelength in the file --
# the problem being that the shape of the array in the file is not padded
# out with dimensions that are length 1 (e.g. a file with 1 wavelength).
# So we pad out the array until it is five-dimensional, and then
# rearrange its axes until its ordering is WTZYX.
def reorderArray(data, size, sequence):
    dimOrder = ['w', 't', 'z', 'y', 'x']
    vals = list(zip(size, dimOrder))
    dataCopy = numpy.array(data)
    # Find missing axes and pad the array until it has 5 axes.
    for val, key in vals[:-2]:
        # The W/T/Z dimensions are left off if they have
        # length 1.
        if val == 1 and len(dataCopy.shape) < 5:
            # The array is missing a dimension, so pad it out.
            dataCopy = numpy.expand_dims(dataCopy, -1)
            if key in sequence:
                # Remove the existing position for that key and add it to the
                # end, since its existing position is actually wrong.
                index = sequence.index(key)
                sequence = sequence[:index] + sequence[index + 1:]
            sequence = sequence + key
    # Generate a list of how we need to reorder the axes.
    ordering = []
    for val, key in vals:
        ordering.append(sequence.index(key))

    return dataCopy.transpose(ordering)
