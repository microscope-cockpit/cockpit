#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford, CNRS
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

import queue
import threading
import time

import numcodecs
import numpy as np
import wx
import zarr

import cockpit.util.datadoc
import cockpit.util.threads
from cockpit import events


## Unique ID for identifying saver instances
uniqueID = 0


## This class simply records all data received during an experiment and saves
# it to disk in MRC format.
class MrcDataSaver:
    ## \param cameras List of CameraHandler instances for the cameras that
    #         will be generating images
    # \param numReps How many times the experiment will be repeated.
    # \param repDuration How long each rep lasts.
    # \param cameraToImagesPerRep Maps camera handlers to how many images to
    #        expect for that camera in a single repeat of the experiment.
    # \param cameraToIgnoredImageIndices Maps camera handlers to indices of
    #        images that we don't actually want to keep.
    # \param runThread Thread that is executing the experiment. When it exits,
    #        we know to stop expecting more images.
    # \param savePath Path to save the incoming data to.
    # \param pixelSizeZ Size of the Z "pixel" (i.e. distance between Z slices).
    # \param titles List of strings to insert into the MRC file's header.
    #        Per the file format, each string can be up to 80 characters long
    #        and there can be up to 10 of them.
    # \param cameraToExcitation Maps camera handlers to the excitation
    #        wavelength used to generate the images it will acquire.
    def __init__(
        self,
        cameras,
        numReps,
        repDuration,
        cameraToImagesPerRep,
        cameraToIgnoredImageIndices,
        runThread,
        savePath,
        pixelSizeZ,
        titles,
        cameraToExcitation,
    ):
        self.cameras = cameras
        self.numReps = numReps
        self.repDuration = repDuration
        self.cameraToImagesPerRep = cameraToImagesPerRep
        self.cameraToIgnoredImageIndices = cameraToIgnoredImageIndices
        self.runThread = runThread

        ## We want to write the excitation wavelength for each image
        ## on the metadata (see issue #290).  We only allow one
        ## excitation wavelength per image.  This is a limitation of
        ## the dv format.  We also assume that all images from a
        ## camera will have the same light source.  This is a
        ## limitation of the cockpit interface.
        self.cameraToExcitation = cameraToExcitation

        ## Maximum size, in megabytes, of each file generated.  If the
        # experiment data exceeds this, then a new file will be opened, and
        # each file will have a suffix appended to it (e.g.  ".001", ".002",
        # etc.). This is not a precise cap, since it only considers the amount
        # of space allocated to image data -- not the header or extended
        # header.
        # The default of a googol megabytes ought to be enough to avoid
        # splitting files if no cap is specified. :)
        self.maxFilesize = 10**100

        global uniqueID
        ## Unique ID for our instance
        self.uniqueID = uniqueID
        uniqueID += 1
        # Find the maximum image size (in pixels) in X and Y. While we're at it,
        # assign a number to each camera, for indexing into our data array
        # later, and figure out how many images per camera we'll actually be
        # *keeping*.
        self.maxWidth, self.maxHeight = 0, 0
        ## We need to establish a consistent ordering for cameras so that
        # each image gets stored in the correct part of the file. This
        # maps camera handlers to indices.
        self.cameraToIndex = {}
        ## Maps camera handlers to total images kept per rep.
        self.cameraToImagesKeptPerRep = {}
        for i, camera in enumerate(self.cameras):
            width, height = camera.getImageSize()
            self.maxWidth = max(width, self.maxWidth)
            self.maxHeight = max(height, self.maxHeight)
            self.cameraToIndex[camera] = i
            self.cameraToImagesKeptPerRep[camera] = self.cameraToImagesPerRep[
                camera
            ] - len(self.cameraToIgnoredImageIndices[camera])
        ## We need this for the upper bound on the array of data we write.
        self.maxImagesPerRep = max(self.cameraToImagesKeptPerRep.values())

        ## Number of bytes to allocate for each image in the file.
        # \todo Assuming unsigned 16-bit integer here.
        self.planeBytes = int(self.maxWidth * self.maxHeight * 2)

        ## Number of timepoints per file, based on the above and
        # self.maxFilesize.
        self.maxRepsPerFile = self.maxFilesize // (
            self.maxImagesPerRep
            * self.planeBytes
            * len(self.cameras)
            / 1024.0
            / 1024.0
        )
        # Now check that there are less than 2^15 -1 images per channel as
        # dv files can't index more than this.
        if (self.maxRepsPerFile * self.maxImagesPerRep) > (2**15) - 1:
            # then ensure that we split files at the end of a time point
            # // operator is floor division
            self.maxRepsPerFile = ((2**15) - 1) // self.maxImagesPerRep
        # Sanity check.
        self.maxRepsPerFile = max(self.maxRepsPerFile, 1)
        ## Whether or not we need to split the data into multiple files.
        self.doNeedToSplitFiles = self.maxRepsPerFile < self.numReps
        # For simplicity's sake, we bring self.maxRepsPerFile down to
        # self.numReps in cases where we only need a single file anyway.
        self.maxRepsPerFile = min(self.numReps, self.maxRepsPerFile)

        ## Maps ints to cameras; the ints represent the order in which the
        # images are stored.
        self.indexToCamera = {v: k for k, v in self.cameraToIndex.items()}
        ## Timestamp of the first image we receive.
        # We need this so we can rebase the timestamps of images to
        # to be relative to the beginning of the experiment -- Python
        # timestamps can't be stored directly as 32-bit floating points without
        # losing a lot of precision. And we want to store image timestamps in
        # the extended header, to help us identify when frames get dropped.
        self.firstTimestamp = None

        ## Time at which we last received an image, so we know when images
        # have stopped arriving.
        self.lastImageTime = time.time()
        self.startTime = time.time()

        ## Filehandles we will write the data to.
        self.filehandles = []
        ## Filenames for same.
        self.filenames = []
        if self.doNeedToSplitFiles:
            # We have multiple filehandles, each with a suffix.
            # A bit tricky here: we want a suffix that has only as many
            # digits as needed, e.g. not doing ".001" when you're only going to
            # use 2 files.
            numFilehandles = int(
                np.ceil(float(self.numReps) / self.maxRepsPerFile)
            )
            numDigits = int(np.ceil(np.log10(numFilehandles)))
            # Generates e.g. "%05d" if we need 5 digits, or "%01d" if we only
            # need 1.
            formatString = "%0" + str(numDigits) + "d"
            for i in range(numFilehandles):
                filename = "%s.%s" % (savePath, formatString % i)
                self.filehandles.append(open(filename, "wb"))
                self.filenames.append(filename)
        else:
            # We have just a single filehandle with the save path as specified.
            self.filehandles.append(open(savePath, "wb"))
            self.filenames.append(savePath)

        ## Lock on writing to each file.
        self.fileLocks = [threading.Lock() for handle in self.filehandles]

        pixelSizeXY = wx.GetApp().Objectives.GetPixelSize()
        lensID = wx.GetApp().Objectives.GetCurrent().lens_ID
        # wavelength should always be on camera even if "0"
        wavelengths = [c.wavelength for c in self.cameras]

        ## Size of one plane's worth of metadata in the extended header.
        numIntegers = 8
        numFloats = 32
        self.extendedBytes = 4 * (numIntegers + numFloats)

        ## MRC header objects for each file.
        self.headers = []
        self.intMetadataBuffers = []
        self.floatMetadataBuffers = []
        for i in range(len(self.filehandles)):
            # Calculate how many timepoints fit into this particular file
            # (potentially different for the final file).
            numTimepoints = self.maxRepsPerFile
            if i == len(self.filehandles) - 1:
                numTimepoints = self.numReps - (
                    self.maxRepsPerFile * (len(self.filehandles) - 1)
                )
            header = cockpit.util.datadoc.makeHeaderForShape(
                (
                    len(self.cameras),
                    numTimepoints,
                    self.maxImagesPerRep,
                    self.maxHeight,
                    self.maxWidth,
                ),
                np.uint16,
                pixelSizeXY,
                pixelSizeZ,
                wavelengths,
            )
            # write the lensID to the header if not zero (meaning undefined)
            if lensID != 0:
                header.LensNum = lensID

            # By default, the headers generated by DataDoc are for files in ZWT
            # order. But for efficient saving of large multi-wavelength files,
            # we need to store in WZT order (where the cameras are as close
            # together as possible).
            header.ImgSequence = 1
            # Write out the "titles" (metadata, like exposure settings)
            tempTitles = list(titles)
            if self.doNeedToSplitFiles and len(titles) < 8:
                # We have room for an extra title indicating where this file
                # falls in the sequence.
                tempTitles.append(
                    "File %d of %d; base timepoint %d"
                    % (i + 1, len(self.filehandles), i * self.maxRepsPerFile)
                )
            header.NumTitles = len(tempTitles)
            header.title[: len(tempTitles)] = tempTitles
            # Write the size of the extended header, in bytes.
            header.next = (
                self.extendedBytes
                * self.maxImagesPerRep
                * len(self.cameras)
                * numTimepoints
            )
            # Number of 32-bit ints and floats in extended header, per plane.
            header.NumIntegers = numIntegers
            header.NumFloats = numFloats

            self.headers.append(header)

            ## This will hold the metadata for one image plane at a
            ## time and will be written into the extended header.  We
            ## could create a new array each time for each plane but
            ## these arrays are small and there will be many image
            ## planes.  We do this to avoid memory fragmentation.
            self.intMetadataBuffers.append(
                np.array([0] * numIntegers, dtype=np.int32)
            )
            floatMetadataBuffer = np.array([0.0] * numFloats, dtype=np.float32)
            floatMetadataBuffer[12] = 1.0  # intensity scaling
            self.floatMetadataBuffers.append(floatMetadataBuffer)

        # Write the headers, to get us started. We will re-write this at the
        # end when we have more metadata to fill in (specifically, the min/max
        # values for each wavelength).
        for i, handle in enumerate(self.filehandles):
            with self.fileLocks[i]:
                cockpit.util.datadoc.writeMrcHeader(self.headers[i], handle)

        ## List of how many images we've received, on a per-camera basis.
        self.imagesReceived = [0] * len(self.cameras)
        ## List of how many images we've written, on a per-camera basis.
        self.imagesKept = [0] * len(self.cameras)
        ## List of functions that receive image data and feed it into
        # self.imagesReceived.
        self.lambdas = []
        ## List of (min, max) tuples, on a per-camera basis, tracking
        # the dimmest and brightest pixels.
        self.minMaxVals = []

        ## True if we should stop collecting data.
        self.shouldAbort = False
        ## True if we are done collecting data.
        self.amDone = False
        ## Queue of (camera index, image data, timestamp) tuples for images
        # that need to be saved
        self.imageQueue = queue.Queue()

        # Use dye name if available, otherwise use camera name.
        names = [camera.dye or camera.name for camera in self.cameras]
        totals = []
        for camera in self.cameras:
            totals.append(self.cameraToImagesKeptPerRep[camera] * self.numReps)
        ## Thread that handles updating the UI.
        self.statusThread = StatusUpdateThread(
            names, totals, self.numReps, self.repDuration
        )

        # Start the data-saving thread.
        self.saveData()

        self.startCollecting()
        self.saveThread = threading.Thread(
            target=self.executeAndSave, name="Experiment-execute-save"
        )
        self.saveThread.start()

    ## Subscribe to the new-camera-image events for the cameras we care about.
    # Save the functions we generate for handling the subscriptions, so we can
    # unsubscribe later. Initialize self.minMaxVals. Start our status-update
    # thread.
    def startCollecting(self):
        for camera in self.cameras:

            def func(data, metadata, camera=camera):
                return self.onImage(self.cameraToIndex[camera], data, metadata)

            self.lambdas.append(func)
            events.subscribe(events.NEW_IMAGE % camera.name, func)

            self.minMaxVals.append((float("inf"), float("-inf")))
        events.subscribe(events.USER_ABORT, self.onAbort)
        self.statusThread.start()

    ## User aborted; stop saving data.
    def onAbort(self):
        self.shouldAbort = True
        self.statusThread.shouldStop = True

    ## Wait for the runThread to finish, then wait a bit longer in case some
    # images are laggardly, before we close our filehandles.
    def executeAndSave(self):
        # Joining the thread doesn't actually work until it has started,
        # hence the delay here.
        time.sleep(0.5)
        self.runThread.join()

        # Wait until it's been a bit without getting any more images in, or
        # until we have all the images we expected to get for each camera.
        while (
            time.time() - self.lastImageTime < self.repDuration + 1.0
        ) or not self.imageQueue.empty():
            #            print ((time.time() - self.startTime),self.repDuration*self.numReps)
            amDone = True
            for camera in self.cameras:
                total = self.imagesKept[self.cameraToIndex[camera]]
                target = self.cameraToImagesKeptPerRep[camera] * self.numReps
                if total != target:
                    # There exists a camera for which we do not have all
                    # images yet.
                    amDone = False
                    break
            if amDone or self.shouldAbort:
                break
            time.sleep(0.01)
        self.amDone = True

        self.cleanup()

        # Determine min/max vals for each wavelength.
        for header in self.headers:
            for i in range(len(self.cameras)):
                # HACK: camera 1 is supposed to get min/max/median. However,
                # computing the median of a large dataset takes a very long
                # time (30s for a 2GB file on a fairly powerful computer),
                # so we just store 0.
                minVal, maxVal = self.minMaxVals[i]
                if i == 0:
                    setattr(header, "mmm1", (minVal, maxVal, 0))
                else:
                    setattr(header, "mm%d" % (i + 1), (minVal, maxVal))
        # Rewrite the headers, now that we know what the min/max values are.
        # Of course, these won't be precisely accurate for every file.
        # \todo Track min/max values on a per-file basis.
        # Then, close the filehandle.
        for i, handle in enumerate(self.filehandles):
            with self.fileLocks[i]:
                cockpit.util.datadoc.writeMrcHeader(self.headers[i], handle)
                handle.close()

    ## Clean up once saving is completed.
    def cleanup(self):
        self.statusThread.shouldStop = True
        for i, camera in enumerate(self.cameras):
            events.unsubscribe(events.NEW_IMAGE % camera.name, self.lambdas[i])
        events.unsubscribe(events.USER_ABORT, self.onAbort)

    ## Receive new data, and add it to the queue.
    def onImage(self, cameraIndex, imageData, metadata):
        self.imageQueue.put((cameraIndex, imageData, metadata))

    ## Continually poll our imageQueue and save data to the file.
    @cockpit.util.threads.callInNewThread
    def saveData(self):
        while not self.amDone:
            if self.shouldAbort:
                # Do nothing.
                return
            cameraIndex, imageData, metadata = self.imageQueue.get()
            timestamp = metadata["timestamp"]
            if self.firstTimestamp is None:
                self.firstTimestamp = timestamp
            # Store the timestamp as a rebased 32-bit float; we can't use
            # 64-bit due to the file format restriction, and if we don't
            # rebase then the numbers are big enough that we lose decimal
            # precision.
            timestamp = timestamp - self.firstTimestamp
            self.writeImage(cameraIndex, imageData, timestamp)

    ## Write a single image to the file.
    def writeImage(self, cameraIndex, imageData, timestamp):
        self.imagesReceived[cameraIndex] += 1
        camera = self.indexToCamera[cameraIndex]
        # First determine if we actually want to keep this image.
        if (
            self.imagesReceived[cameraIndex]
            % self.cameraToImagesPerRep[camera]
        ) in self.cameraToIgnoredImageIndices[camera]:
            # This image is one that should be discarded.
            return

        # Calculate the time and Z indices for the new image. This will in turn
        # help us to calculate which file to write to and the offset of the
        # image in the file.
        numImages = self.imagesKept[cameraIndex]
        timepoint = numImages // self.maxImagesPerRep
        fileIndex = timepoint // self.maxRepsPerFile
        # Rebase the timepoint to be relative to the beginning of this specific
        # file.
        timepoint -= fileIndex * self.maxRepsPerFile
        zIndex = numImages % self.cameraToImagesKeptPerRep[camera]

        numCameras = len(self.cameras)
        planeIndex = (
            int(timepoint * self.maxImagesPerRep * numCameras)
            + (zIndex * numCameras)
            + cameraIndex
        )

        ## Offsets for the plane metadata in the extended header, and
        ## for the plane data in the image section.  1024 is the
        ## length of the base header.
        metadataOffset = 1024 + (planeIndex * self.extendedBytes)
        dataOffset = (
            1024
            + int(self.headers[fileIndex].next)
            + (planeIndex * self.planeBytes)
        )

        height, width = imageData.shape

        # Pad with zeros. I wouldn't normally think this would be
        # necessary, but we get "invalid argument" errors when writing
        # to the filehandle if we don't.
        # \todo Figure out why this is necessary.
        paddedBuffer = np.zeros(
            (self.maxHeight, self.maxWidth), dtype=np.uint16
        )
        paddedBuffer[:height, :width] = imageData

        imageMin = imageData.min()
        imageMax = imageData.max()

        ex_wavelength = self.cameraToExcitation[camera]
        em_wavelength = camera.wavelength

        with self.fileLocks[fileIndex]:
            handle = self.filehandles[fileIndex]

            ## The extended header has the following structure per
            ## plane (see issue #290):
            ##
            ##     8 32bit signed integers whose meaning we don't
            ##     know.  Often are all set to zero.
            ##
            ##     Followed by 32 32bit floats.  We only what the
            ##     first 14 are:
            ##
            ##     photosensor reading (typically in mV)
            ##     elapsed time (seconds since experiment began)
            ##     x stage coordinates
            ##     y stage coordinates
            ##     z stage coordinates
            ##     minimum intensity
            ##     maximum intensity
            ##     mean intensity
            ##     exposure time (seconds)
            ##     neutral density (fraction of 1 or percentage)
            ##     excitation wavelength
            ##     emission wavelength
            ##     intensity scaling (usually 1)
            ##     energy conversion factor (usually 1)
            ##
            ## Experience from inspecting actual dv files from API
            ## systems, tells us that we can leave most of them at
            ## zero.
            intMetadataBuffer = self.intMetadataBuffers[fileIndex]
            floatMetadataBuffer = self.floatMetadataBuffers[fileIndex]
            floatMetadataBuffer[1] = timestamp
            floatMetadataBuffer[5] = imageMin
            floatMetadataBuffer[6] = imageMax
            # TODO floatMetadataBuffer[8] could be exposure time in seconds
            floatMetadataBuffer[10] = ex_wavelength
            floatMetadataBuffer[11] = em_wavelength

            try:
                handle.seek(metadataOffset)
                handle.write(intMetadataBuffer)
                handle.write(floatMetadataBuffer)
                handle.seek(dataOffset)
                handle.write(paddedBuffer)
            except Exception as e:
                print("Error writing image:", e)
                raise e

            self.imagesKept[cameraIndex] += 1
            self.lastImageTime = time.time()

            curMin, curMax = self.minMaxVals[cameraIndex]
            self.minMaxVals[cameraIndex] = (
                min(curMin, imageMin),
                max(curMax, imageMax),
            )

        # Update the status text. But first, check for abort/experiment
        # completion, since we may actually be done now and we don't want
        # a misleading status text.
        if self.shouldAbort or self.amDone:
            return
        self.statusThread.newImage(cameraIndex)

    ## Return a list of the filenames we are writing to.
    def getFilenames(self):
        return self.filenames


## This class simply records all data received during an experiment and saves
# it to disk in ome-zarr format.
class ZarrDataSaver:
    ## \param cameras List of CameraHandler instances for the cameras that
    #         will be generating images
    # \param numReps How many times the experiment will be repeated.
    # \param repDuration How long each rep lasts.
    # \param cameraToImagesPerRep Maps camera handlers to how many images to
    #        expect for that camera in a single repeat of the experiment.
    # \param cameraToIgnoredImageIndices Maps camera handlers to indices of
    #        images that we don't actually want to keep.
    # \param runThread Thread that is executing the experiment. When it exits,
    #        we know to stop expecting more images.
    # \param savePath Path to save the incoming data to.
    # \param pixelSizeXY Size of the XY "pixel".
    # \param pixelSizeZ Size of the Z "pixel" (i.e. distance between Z slices).
    # \param omeMetadata OME-XML Metadata to be included in the OME-Zarr file.
    # \param downscale Downscaling factor for x and y axes
    # \param maxLayer Number of downscalings. We are defaulting here to 2
    # \param downscaleMethod Downscaling method. Default is 'nearest'
    # \param chunkShape Output chunk shape
    # \param compression Compressor to be used, defaults to numcodecs.Blosc()
    # \param overwrite Overwrite existing files
    def __init__(
        self,
        cameras,
        numReps,
        repDuration,
        cameraToImagesPerRep,
        cameraToIgnoredImageIndices,
        runThread,
        savePath,
        pixelSizeXY,
        pixelSizeZ,
        omeMetadata=None,
        downscale=2,
        maxLayer=2,
        downscaleMethod="nearest",
        chunkShape=(1, 1024, 1024),
        compression=numcodecs.Blosc(),
        overwrite=True,
    ):
        self.cameras = cameras
        self.numReps = numReps
        self.repDuration = repDuration
        self.cameraToImagesPerRep = cameraToImagesPerRep
        self.cameraToIgnoredImageIndices = cameraToIgnoredImageIndices
        self.runThread = runThread

        global uniqueID
        # Unique ID for our instance
        self.uniqueID = uniqueID
        uniqueID += 1
        # Assign a number to each camera, for indexing into our data array
        # later, and figure out how many images per camera we'll actually be
        # *keeping*.
        ## We need to establish a consistent ordering for cameras so that
        # each image gets stored in the correct part of the file. This
        # maps camera handlers to indices.
        self.cameraToIndex = {}
        ## Maps camera handlers to total images kept per rep.
        self.cameraToImagesKeptPerRep = {}
        for i, camera in enumerate(self.cameras):
            self.cameraToIndex[camera] = i
            self.cameraToImagesKeptPerRep[camera] = self.cameraToImagesPerRep[
                camera
            ] - len(self.cameraToIgnoredImageIndices[camera])
        # We need this for the upper bound on the array of data we write.
        self.maxImagesPerRep = max(self.cameraToImagesKeptPerRep.values())

        # Maps ints to cameras; the ints represent the order in which the
        # images are stored.
        self.indexToCamera = {v: k for k, v in self.cameraToIndex.items()}
        # Timestamp of the first image we receive.
        # We need this so we can rebase the timestamps of images to
        # to be relative to the beginning of the experiment -- Python
        # timestamps can't be stored directly as 32-bit floating points without
        # losing a lot of precision. And we want to store image timestamps in
        # the extended header, to help us identify when frames get dropped.
        self.firstTimestamp = None

        # Time at which we last received an image, so we know when images
        # have stopped arriving.
        self.lastImageTime = time.time()
        self.startTime = time.time()

        self.pixelSizeXY = pixelSizeXY
        self.pixelSizeZ = pixelSizeZ

        # ome-zarr specific settings
        self.scaler = scale.Scaler(
            downscale=downscale, max_layer=maxLayer, method=downscaleMethod
        )
        self.coordinateTransforms = [
            [
                {
                    "scale": [pixelSizeZ, pixelSizeXY, pixelSizeXY],
                    "type": "scale",
                }
            ],
            [
                {
                    "scale": [
                        pixelSizeZ,
                        pixelSizeXY * downscale,
                        pixelSizeXY * downscale,
                    ],
                    "type": "scale",
                }
            ],
        ]

        self.storageOptions = {
            "chunks": chunkShape,
            "compression": compression,
            "overwrite": overwrite,
        }

        self.savePath = savePath
        # Parse the url as a zarr store. Note that "mode = 'w'" enables writing to this store.
        self.zarrStore = parse_url(self.savePath, mode="w").store
        self.zarrRoot = zarr.open_group(self.zarrStore)

        # List of how many images we've received, on a per-camera basis.
        self.imagesReceived = [0] * len(self.cameras)
        # List of how many images we've written, on a per-camera basis.
        self.imagesKept = [0] * len(self.cameras)
        # List of functions that receive image data and feed it into
        # self.imagesReceived.
        self.lambdas = []
        # List of (min, max) tuples, on a per-camera basis, tracking
        # the dimmest and brightest pixels.
        self.minMaxVals = []

        # True if we should stop collecting data.
        self.shouldAbort = False
        # True if we are done collecting data.
        self.amDone = False
        # Queue of (camera index, image data, timestamp) tuples for images
        # that need to be saved
        self.imageQueue = queue.Queue()

        # Use dye name if available, otherwise use camera name.
        names = [camera.dye or camera.name for camera in self.cameras]
        totals = []
        for camera in self.cameras:
            totals.append(self.cameraToImagesKeptPerRep[camera] * self.numReps)
        # Thread that handles updating the UI.
        self.statusThread = StatusUpdateThread(
            names, totals, self.numReps, self.repDuration
        )

        # Start the data-saving thread.
        self.saveData()

    # Subscribe to the new-camera-image events for the cameras we care about.
    # Save the functions we generate for handling the subscriptions, so we can
    # unsubscribe later. Initialize self.minMaxVals. Start our status-update
    # thread.
    def startCollecting(self):
        for camera in self.cameras:

            def func(data, metadata, camera=camera):
                return self.onImage(self.cameraToIndex[camera], data, metadata)

            self.lambdas.append(func)
            events.subscribe(events.NEW_IMAGE % camera.name, func)

            self.minMaxVals.append((float("inf"), float("-inf")))
        events.subscribe(events.USER_ABORT, self.onAbort)
        self.statusThread.start()

    # User aborted; stop saving data.
    def onAbort(self):
        self.shouldAbort = True
        self.statusThread.shouldStop = True

    # Wait for the runThread to finish, then wait a bit longer in case some
    # images are laggardly, before we close our filehandles.
    def executeAndSave(self):
        # Joining the thread doesn't actually work until it has started,
        # hence the delay here.
        time.sleep(0.5)
        self.runThread.join()

        # Wait until it's been a bit without getting any more images in, or
        # until we have all the images we expected to get for each camera.
        while (
            time.time() - self.lastImageTime < self.repDuration + 1.0
        ) or not self.imageQueue.empty():
            amDone = True
            for camera in self.cameras:
                total = self.imagesKept[self.cameraToIndex[camera]]
                target = self.cameraToImagesKeptPerRep[camera] * self.numReps
                if total != target:
                    # There exists a camera for which we do not have all
                    # images yet.
                    amDone = False
                    break
            if amDone or self.shouldAbort:
                break
            time.sleep(0.01)
        self.amDone = True

        self.cleanup()

    # Clean up once saving is completed.
    def cleanup(self):
        self.statusThread.shouldStop = True
        for i, camera in enumerate(self.cameras):
            events.unsubscribe(events.NEW_IMAGE % camera.name, self.lambdas[i])
        events.unsubscribe(events.USER_ABORT, self.onAbort)

    # Receive new data, and add it to the queue.
    def onImage(self, cameraIndex, imageData, metadata):
        self.imageQueue.put((cameraIndex, imageData, metadata))

    # Continually poll our imageQueue and save data to the file.
    @cockpit.util.threads.callInNewThread
    def saveData(self):
        while not self.amDone:
            if self.shouldAbort:
                # Do nothing.
                return
            cameraIndex, imageData, metadata = self.imageQueue.get()
            timestamp = metadata["timestamp"]
            if self.firstTimestamp is None:
                self.firstTimestamp = timestamp
            # Store the timestamp as a rebased 32-bit float; we can't use
            # 64-bit due to the file format restriction, and if we don't
            # rebase then the numbers are big enough that we lose decimal
            # precision.
            timestamp = timestamp - self.firstTimestamp
            self.writeImage(cameraIndex, imageData, timestamp)

    # Write a single image to the file.
    def writeImage(self, cameraIndex, imageData, timestamp):
        self.imagesReceived[cameraIndex] += 1
        camera = self.indexToCamera[cameraIndex]
        # First determine if we actually want to keep this image.
        if (
            self.imagesReceived[cameraIndex]
            % self.cameraToImagesPerRep[camera]
        ) in self.cameraToIgnoredImageIndices[camera]:
            # This image is one that should be discarded.
            return

        # Calculate the time and Z indices for the new image. This will in turn
        # help us to calculate which file to write to and the offset of the
        # image in the file.
        numImages = self.imagesKept[cameraIndex]
        timepoint = numImages // self.maxImagesPerRep
        fileIndex = timepoint // self.maxRepsPerFile
        # Rebase the timepoint to be relative to the beginning of this specific
        # file.
        timepoint -= fileIndex * self.maxRepsPerFile
        zIndex = numImages % self.cameraToImagesKeptPerRep[camera]

        numCameras = len(self.cameras)
        planeIndex = (
            int(timepoint * self.maxImagesPerRep * numCameras)
            + (zIndex * numCameras)
            + cameraIndex
        )

        height, width = imageData.shape

        # Pad with zeros. I wouldn't normally think this would be
        # necessary, but we get "invalid argument" errors when writing
        # to the filehandle if we don't.
        # \todo Figure out why this is necessary.
        paddedBuffer = np.zeros(
            (self.maxHeight, self.maxWidth), dtype=np.uint16
        )
        paddedBuffer[:height, :width] = imageData

        imageMin = imageData.min()
        imageMax = imageData.max()

        ex_wavelength = self.cameraToExcitation[camera]
        em_wavelength = camera.wavelength

        with self.fileLocks[fileIndex]:
            handle = self.filehandles[fileIndex]

            ## The extended header has the following structure per
            ## plane (see issue #290):
            ##
            ##     8 32bit signed integers whose meaning we don't
            ##     know.  Often are all set to zero.
            ##
            ##     Followed by 32 32bit floats.  We only what the
            ##     first 14 are:
            ##
            ##     photosensor reading (typically in mV)
            ##     elapsed time (seconds since experiment began)
            ##     x stage coordinates
            ##     y stage coordinates
            ##     z stage coordinates
            ##     minimum intensity
            ##     maximum intensity
            ##     mean intensity
            ##     exposure time (seconds)
            ##     neutral density (fraction of 1 or percentage)
            ##     excitation wavelength
            ##     emission wavelength
            ##     intensity scaling (usually 1)
            ##     energy conversion factor (usually 1)
            ##
            ## Experience from inspecting actual dv files from API
            ## systems, tells us that we can leave most of them at
            ## zero.
            intMetadataBuffer = self.intMetadataBuffers[fileIndex]
            floatMetadataBuffer = self.floatMetadataBuffers[fileIndex]
            floatMetadataBuffer[1] = timestamp
            floatMetadataBuffer[5] = imageMin
            floatMetadataBuffer[6] = imageMax
            # TODO floatMetadataBuffer[8] could be exposure time in seconds
            floatMetadataBuffer[10] = ex_wavelength
            floatMetadataBuffer[11] = em_wavelength

            try:
                handle.seek(metadataOffset)
                handle.write(intMetadataBuffer)
                handle.write(floatMetadataBuffer)
                handle.seek(dataOffset)
                handle.write(paddedBuffer)
            except Exception as e:
                print("Error writing image:", e)
                raise e

            self.imagesKept[cameraIndex] += 1
            self.lastImageTime = time.time()

            curMin, curMax = self.minMaxVals[cameraIndex]
            self.minMaxVals[cameraIndex] = (
                min(curMin, imageMin),
                max(curMax, imageMax),
            )

        # Update the status text. But first, check for abort/experiment
        # completion, since we may actually be done now and we don't want
        # a misleading status text.
        if self.shouldAbort or self.amDone:
            return
        self.statusThread.newImage(cameraIndex)

    ## Return a list of the filenames we are writing to.
    def getFilenames(self):
        return self.filenames


## This class simply records all data received during an experiment and saves
# it to disk in ome-zarr format.
class ZarrDataSaver:
    ## \param cameras List of CameraHandler instances for the cameras that
    #         will be generating images
    # \param numReps How many times the experiment will be repeated.
    # \param repDuration How long each rep lasts.
    # \param cameraToImagesPerRep Maps camera handlers to how many images to
    #        expect for that camera in a single repeat of the experiment.
    # \param cameraToIgnoredImageIndices Maps camera handlers to indices of
    #        images that we don't actually want to keep.
    # \param runThread Thread that is executing the experiment. When it exits,
    #        we know to stop expecting more images.
    # \param savePath Path to save the incoming data to.
    # \param pixelSizeXY Size of the XY "pixel".
    # \param pixelSizeZ Size of the Z "pixel" (i.e. distance between Z slices).
    # \param omeMetadata OME-XML Metadata to be included in the OME-Zarr file.
    # \param downscale Downscaling factor for x and y axes
    # \param maxLayer Number of downscalings. We are defaulting here to 2
    # \param downscaleMethod Downscaling method. Default is 'nearest'
    # \param chunkShape Output chunk shape
    # \param compression Compressor to be used, defaults to numcodecs.Blosc()
    # \param overwrite Overwrite existing files
    def __init__(
        self,
        exposureSettings,
        numReps,
        repDuration,
        cameraToImagesPerRep,
        cameraToIgnoredImageIndices,
        runThread,
        savePath,
        pixelSizeXY,
        sliceHeight,
        omeMetadata=None,
        downscale=None,
        maxLayer=1,
        downscaleMethod="nearest",
        compression="blosc",
        overwrite=True,
    ):
        self._exposureSettings = exposureSettings
        self._numReps = numReps
        self._repDuration = repDuration
        self._cameraToImagesPerRep = cameraToImagesPerRep
        self._cameraToIgnoredImageIndices = cameraToIgnoredImageIndices
        self.runThread = runThread
        self.savePath = savePath
        self._pixelSizeXY = pixelSizeXY
        self._sliceHeight = sliceHeight

        global uniqueID
        # Unique ID for our instance
        self.uniqueID = uniqueID
        uniqueID += 1

        # We need this so we can rebase the timestamps of images to
        # to be relative to the beginning of the experiment -- Python
        # timestamps can't be stored directly as 32-bit floating points without
        # losing a lot of precision. And we want to store image timestamps in
        # the extended header, to help us identify when frames get dropped.
        self._firstTimestamp = None

        # Time at which we last received an image, so we know when images
        # have stopped arriving.
        self._lastImageTime = time.time()
        self._startTime = time.time()

        # Exposure settings are List of ([cameras], [(light, exposure time)])
        # tuples describing how to take images. We need to transform this into
        # a list of channels, which is a list of (camera, [light, exposure time])
        # tuples. Those will map to channels in the data.
        self._channels = []
        for cameras, exposure in self._exposureSettings:
            self._channels.extend((camera, exposure) for camera in cameras)

        # Some experiments are triggering images that are not ment to be kept.
        # For each camera, find the number of images that are going to be kept
        self._cameraToImagesKeptPerRep = {
            camera: self._cameraToImagesPerRep[camera]
            - len(self._cameraToIgnoredImageIndices[camera])
            for camera in self._cameraToImagesPerRep
        }

        # Map cameras to the channel index where they are used
        self._camerasToChannelIds()

        # Calculate what are going to be the shapes of the channels
        self._computeChannelShapes()

        # We need to know how many images we are going to keep per camera
        self._cameraToImagesKept = {
            camera: imagesPerRep * self._numReps
            for camera, imagesPerRep in self._cameraToImagesKeptPerRep.items()
        }
        # Dict to keep track of images we've received, on a per-camera basis.
        self._imagesReceived = {
            camera: 0 for camera in self._cameraToChannelIds
        }
        # Dict to keep track of how many images we've written, on a per-camera basis.
        self._imagesKept = {camera: 0 for camera in self._cameraToChannelIds}

        # List of functions that receive image data.
        self._imageReceivingFuncs = []
        for camera in self._cameraToChannelIds:

            def func(data, metadata, camera=camera):
                return self.onImage(camera, data, metadata)

            self._imageReceivingFuncs.append(func)
            events.subscribe(events.NEW_IMAGE % camera.name, func)

        # Zarr specific settings
        # Scaling and compression
        self.compression = compression
        self.overwrite = overwrite

        # zarr specific settings
        # Shape and chunking
        self.arrayShape = (
            self._numReps,  # T: timepoints
            len(self._channels),  # C: number of channels
            self.channelShapes[0][0],  # Z: number of slices
            self.channelShapes[0][1],  # Y
            self.channelShapes[0][2],  # X
        )
        self.chunkShape = (
            1,
            1,
            1,
            self.channelShapes[0][1],
            self.channelShapes[0][2],
        )
        # self.scaler = scale.Scaler(
        #     downscale=downscale,
        #     max_layer=maxLayer,
        #     method=downscaleMethod
        # )
        # self.coordinateTransforms = [
        #     [{'scale': [sliceHeight, pixelSizeXY, pixelSizeXY], 'type': 'scale'}],
        # ]
        # self.storageOptions = {
        #     "chunks": chunkShape,
        #     "compression": compression,
        #     "overwrite": overwrite,
        # }
        self._createZarrArray()

        # A ThreadLock to protect some operations.
        self._threadLock = threading.Lock()

        ## Flag to indicate if we should stop collecting data because of:
        # user abort
        self.shouldAbort = False
        # experiment done.
        self.amDone = False
        # Queue of (camera index, image data, timestamp) tuples for images
        # that need to be saved
        self._imageQueue = queue.Queue()

        # Thread that handles updating the UI.
        # TODO: This might be simplified by passing to the StatusUpdateThread
        #  a dictionary with the camera name and the target number of images to be kept.
        #  Also because the total of expected images is used later in the executeAndSave method.
        self.statusThread = StatusUpdateThread(
            [camera.dye or camera.name for camera in self._cameraToChannelIds],
            list(self._cameraToImagesKept.values()),
            self._numReps,
            self._repDuration,
        )

        # Start the data-saving thread.
        self.saveData()

        # Start our status-update thread.
        events.subscribe(events.USER_ABORT, self.onAbort)
        self.statusThread.start()

        self.saveThread = threading.Thread(
            target=self.executeAndSave, name="Experiment-execute-save"
        )
        self.saveThread.start()

    def _camerasToChannelIds(self):
        """
        Map every camera to the index of the channel where they are used
        """
        self._cameraToChannelIds = {
            camera: [] for camera in self._cameraToImagesKeptPerRep
        }
        for channelId, channel in enumerate(self._channels):
            self._cameraToChannelIds[channel[0]] += [channelId]

    def _computeChannelShapes(self):
        """
        Calculate the shape of the channel based on the input arguments.
        If the channel shape is not the same for every channel we raise
        an Exception.
        """
        # We expect that every channel has the same number of images (typically
        # a z-stack). So the expected images per channel must match the expected
        # images per camera divided by the number of channels where the camera is
        # used.
        self.channelShapes = []
        for channel in self._channels:
            camera = channel[0]
            if (
                self._cameraToImagesKeptPerRep[camera]
                % len(self._cameraToChannelIds[camera])
                != 0
            ):
                raise ValueError(
                    "The number of images per camera is not divisible by the number of channels"
                )
            shape_z = self._cameraToImagesKeptPerRep[camera] // len(
                self._cameraToChannelIds[camera]
            )
            shape_xy = camera.getImageSize()
            self.channelShapes.append((shape_z, shape_xy[0], shape_xy[1]))

        # We want to make sure that the shape in z is consistent across all
        # channels. This might be supported in the future, but for now we assume
        # that all channels have the same number of slices.
        if any(
            channel_shape[0] != self.channelShapes[0][0]
            for channel_shape in self.channelShapes
        ):
            raise NotImplementedError(
                "The number of slices is not the same for all channels"
            )

        # We want to make sure that the x and y dimensions are consistent across all
        # channels. This might be supported in the future, but for now we assume
        # that all channels have the same x and y dimensions.
        if any(
            channel_shape[1] != self.channelShapes[0][1]
            or channel_shape[2] != self.channelShapes[0][2]
            for channel_shape in self.channelShapes
        ):
            raise NotImplementedError(
                "The x and y dimensions are not the same for all channels"
            )

    # User aborted; stop saving data.
    def onAbort(self):
        self.shouldAbort = True
        self.statusThread.shouldStop = True

    # Wait for the runThread to finish, then wait a bit longer in case some
    # images are laggardly, before we close our filehandles.
    def executeAndSave(self):
        # Joining the thread doesn't actually work until it has started,
        # hence the delay here.
        time.sleep(0.5)
        self.runThread.join()

        # Wait until it's been a bit without getting any more images in, or
        # until we have all the images we expected to get for each camera.
        while (
            time.time() - self._lastImageTime < self._repDuration + 1.0
        ) or not self._imageQueue.empty():
            amDone = True
            if self._imagesKept != self._cameraToImagesKept:
                # There exists a camera for which we do not have all
                # images yet.
                amDone = False
            if amDone or self.shouldAbort:
                break
            time.sleep(0.01)
        self.amDone = True

        self.cleanup()

    # Clean up once saving is completed.
    def cleanup(self):
        self.statusThread.shouldStop = True
        for i, camera in enumerate(self._cameraToChannelIds):
            events.unsubscribe(
                events.NEW_IMAGE % camera.name, self._imageReceivingFuncs[i]
            )
        events.unsubscribe(events.USER_ABORT, self.onAbort)

    # Receive new data, and add it to the queue.
    def onImage(self, camera, imageData, metadata):
        self._imageQueue.put((camera, imageData, metadata))

    @cockpit.util.threads.callInMainThread
    def _createZarrArray(self):
        self._zarrRoot = zarr.create_group(
            store=self.savePath,
            overwrite=self.overwrite,
            attributes=self._constructOMEAttributes(),
        )
        self._zarrArray = self._zarrRoot.create_array(
            name="0",
            dimension_names=["t", "c", "z", "y", "x"],
            shape=self.arrayShape,
            chunks=self.chunkShape,
            # compressor=self.compression,
            overwrite=self.overwrite,
            dtype="uint16",
        )

    def _constructOMEAttributes(self):
        omeMetadata = {
            "ome": {
                "version": "0.5",
                # "series": ["0", "1"],  # TODO: Series are to be put here
                "multiscales": [
                    {
                        "name": "5D",
                        "axes": [
                            dict(name="t", type="time", unit="second"),
                            dict(name="c", type="channel"),
                            dict(name="z", type="space", unit="micrometer"),
                            dict(name="y", type="space", unit="micrometer"),
                            dict(name="x", type="space", unit="micrometer"),
                        ],
                        "datasets": [
                            {
                                "path": "0",
                                "coordinateTransformations": [
                                    {
                                        "type": "scale",
                                        "scale": [
                                            self._repDuration,
                                            1.0,
                                            self._sliceHeight,
                                            self._pixelSizeXY,
                                            self._pixelSizeXY,
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        }
        return omeMetadata

    # Continually poll our imageQueue and save data to the file.
    @cockpit.util.threads.callInNewThread
    def saveData(self):
        while not self.amDone:
            if self.shouldAbort:
                # Do nothing.
                return
            camera, imageData, metadata = self._imageQueue.get()
            timestamp = metadata["timestamp"]
            if self._firstTimestamp is None:
                self._firstTimestamp = timestamp
            # Store the timestamp as a rebased 32-bit float; we can't use
            # 64-bit due to the file format restriction, and if we don't
            # rebase then the numbers are big enough that we lose decimal
            # precision.
            timestamp = timestamp - self._firstTimestamp
            self.writeImage(camera, imageData, timestamp)

    # Write a single image to the file.
    def writeImage(self, camera, imageData, timestamp):
        self._imagesReceived[camera] += 1
        # First determine if we actually want to keep this image.
        if (
            self._imagesReceived[camera] % self._cameraToImagesPerRep[camera]
        ) in self._cameraToIgnoredImageIndices[camera]:
            # This image should be discarded.
            return

        # Calculate the time and Z indices for the new image. This will in turn
        # help us to calculate which file to write to and the offset of the
        # image in the file.
        imageIndex = self._imagesKept[camera]
        timeIndex = imageIndex // self._cameraToImagesKeptPerRep[camera]
        channelZReminder = imageIndex % self._cameraToImagesKeptPerRep[camera]
        channelIndex = self._cameraToChannelIds[camera][
            channelZReminder
            // self.channelShapes[0][
                0
            ]  # Only takes into account one possible z-shape per channel or camera
        ]
        zIndex = (
            channelZReminder % self.channelShapes[0][0]
        )  # Only takes into account one possible z-shape per channel or camera

        with self._threadLock:
            self.appendImageToZarr(timeIndex, channelIndex, zIndex, imageData)
            self._imagesKept[camera] += 1
            self._lastImageTime = time.time()

        # Update the status text. But first, check for abort/experiment
        # completion, since we may actually be done now and we don't want
        # a misleading status text.
        if self.shouldAbort or self.amDone:
            return
        self.statusThread.newImage(
            list(self._cameraToImagesKeptPerRep.keys()).index(camera)
        )

    @cockpit.util.threads.callInMainThread
    def appendImageToZarr(self, timeIndex, channelIndex, zIndex, imageData):
        """
        Append a new image to the zarr array.
        We call this in the main thread, so we can ensure it is run in the
        asyncio event loop.
        """
        self._zarrArray[timeIndex, channelIndex, zIndex] = imageData

    # Return a list of the filenames we are writing to.
    def getFilenames(self):
        return self.savePath


# This thread handles telling the saving status light to update twice per
# second.
class StatusUpdateThread(threading.Thread):
    def __init__(self, cameraNames, totals, numReps, repDuration):
        super().__init__()
        ## List of names of the cameras.
        self.cameraNames = cameraNames
        ## List of images received per camera.
        self.imagesReceived = [0 for name in self.cameraNames]
        ## Lock on updating the above.
        self.imageCountLock = threading.Lock()
        ## List of total images expected per camera.
        self.totals = totals
        self.numReps = numReps
        self.repDuration = repDuration
        self.startTime = time.time()
        ## Set to True to end the thread.
        self.shouldStop = False
        self.name = "DataSaver-status"

    def run(self):
        prevCounts = list(self.imagesReceived)
        self.updateText()
        count = 0
        while not self.shouldStop:
            if prevCounts != self.imagesReceived:
                # Have received new images since the last update;
                # update the display.
                count = 0
                with self.imageCountLock:
                    self.updateText()
                    prevCounts = list(self.imagesReceived)
            else:
                # No images; wait a bit, but update wait text every 0.5s
                time.sleep(0.1)
                count = count + 1
                if count == 5:
                    count = 0
                    self.updateText()
        # Clear the status light.
        events.publish(events.UPDATE_STATUS_LIGHT, "image count", "")

    ## Push a new text to the status light.
    def updateText(self):
        statusText = []
        for i, name in enumerate(self.cameraNames):
            curCount = self.imagesReceived[i]
            maxCount = self.totals[i]
            statusText.append("%s: %d/%d" % (name, curCount, maxCount))
        if (sum(self.imagesReceived) % (maxCount / self.numReps)) == 0:
            # we are between reps
            repTime = (time.time() - self.startTime) % self.repDuration
            timeleft = self.repDuration - repTime
            statusText.append("waiting %.0fs for next repeat" % timeleft)
        events.publish(
            events.UPDATE_STATUS_LIGHT, "image count", " | ".join(statusText)
        )

    ## Update our image count.
    def newImage(self, index):
        with self.imageCountLock:
            self.imagesReceived[index] += 1
