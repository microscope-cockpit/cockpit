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

"""Generates offset/gain correction files (which add an offset to
pixel values and then multiply them by a gain factor).
"""

from cockpit.experiment import actionTable
import decimal
from cockpit import events
from cockpit.experiment import experiment
from cockpit.gui import guiUtils
import cockpit.handlers.camera
import cockpit.util.datadoc
import cockpit.util.threads
import cockpit.util.userConfig

import numpy
import threading
import time
import wx


## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Offset/gain correction file'


## This class collects the data needed to generate an offset and gain
# correction file. It takes exposures of some flat illumination source (e.g. 
# a Chroma slide) at varying exposure times, to characterize the response of 
# the cameras to incident light. 
class OffsetGainCorrectionExperiment(experiment.Experiment):
    ## \param numExposures How many images to take for each exposure time.
    # \param exposureMultiplier Factor by which to increase exposure time for
    #        each step.
    # \param maxIntensity Once the max intensity exceeds this value for a 
    #        given camera, we stop collecting data for it.
    # \param cosmicRayThreshold If any pixels are more than this many 
    #        standard deviations away from the median of the overall image, then
    #        the image is discarded.
    # \param numCollections Maximum number of different exposure times to try,
    #        assuming no other stopping condition is hit first.
    # \param shouldPreserveIntermediaryFiles If True, then save the raw data
    #        to a separate file, alongside the actual result file.
    def __init__(self, cameras, lights, exposureSettings, numExposures, 
            savePath, exposureMultiplier = 2, maxIntensity = 2 ** 12, 
            cosmicRayThreshold = 10, numCollections = 5,
            shouldPreserveIntermediaryFiles = False, **kwargs):
        # Note we fill in some dummy values here since we don't actually 
        # move the stage during this experiment, and we handle data saving
        # manually. Some of these values may actually have been passed in via
        # the kwargs parameter (since our caller may have generic code for
        # setting up arbitrary experiments that assumes e.g. a Z stack), but
        # we ignore them.
        super().__init__(numReps = 1, repDuration = 0,
                zPositioner = None, altBottom = 0, zHeight = 0, sliceHeight = 0,
                cameras = cameras, lights = lights,
                exposureSettings = exposureSettings)
        self.numExposures = numExposures
        self.savePath = savePath
        self.exposureMultiplier = decimal.Decimal(exposureMultiplier)
        self.maxIntensity = maxIntensity
        self.cosmicRayThreshold = cosmicRayThreshold
        self.numCollections = numCollections
        self.shouldPreserveIntermediaryFiles = shouldPreserveIntermediaryFiles

        ## Maps camera handlers to lists of averaged images.
        self.camToAverages = dict([(cam, []) for cam in cameras])
        ## Current image accumulator. This is wiped with each iteration of 
        # the experiment. Maps camera handlers to lists of images.
        self.camToImages = None
        ## Maps camera handlers to number of images received thus far.
        self.camToNumImagesReceived = None
        ## Maps cameras to locks around the above two fields.
        self.camToLock = {}
        ## Maps camera handlers to functions to record their images.
        self.camToFunc = {}
        for camera in self.cameras:
            self.camToFunc[camera] = lambda image, timestamp, camera = camera: self.recordImage(image, camera)

        ## Thread for tracking when we're done receiving images.
        self.doneReceivingThread = None
        ## Time we last received an image, used in the above thread.
        self.lastImageTime = None


    ## Broadly similar to Experiment.run(), but we generate and execute multiple
    # tables.
    @cockpit.util.threads.callInNewThread
    def run(self):
        # For debugging purposes
        experiment.lastExperiment = self
        
        self.sanityCheckEnvironment()
        self.prepareHandlers()

        self.cameraToReadoutTime = dict([(c, c.getTimeBetweenExposures(isExact = True)) for c in self.cameras])
        for camera, readTime in self.cameraToReadoutTime.items():
            if type(readTime) is not decimal.Decimal:
                raise RuntimeError("Camera %s did not provide an exact (decimal.Decimal) readout time" % camera.name)

        # Start out with no-exposure-time images to get a measured offset.
        multiplier = 0
        for camera, func in self.camToFunc.items():
            events.subscribe(events.NEW_IMAGE % camera.name, func)
        activeCameras = set(self.cameras)
        for i in range(self.numCollections):
            if not activeCameras or self.shouldAbort:
                break
            print ("Running with cams",activeCameras)
            self.camToImages = {}
            self.camToNumImagesReceived = {}
            self.camToLock = {}
            for camera in activeCameras:
                # Prepare a memory buffer to store images in.
                width, height = camera.getImageSize()
                self.camToImages[camera] = numpy.zeros((self.numExposures, height, width))
                self.camToNumImagesReceived[camera] = 0
                self.camToLock[camera] = threading.Lock()
                # Indicate any frame transfer cameras for reset at start of
                # table.
                if camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_AFTER:
                    self.cameraToIsReady[camera] = False

            self.table = self.generateActions(multiplier, activeCameras)
            self.table.sort()
            self.examineActions()
            self.table.sort()
            self.table.enforcePositiveTimepoints()
            self.lastMinuteActions()
            self.doneReceivingThread = threading.Thread(target = self.waiter)
            self.doneReceivingThread.start()
            self.execute()
            # Wait until it's been a short time after the last received image.
            self.doneReceivingThread.join()
            
            if multiplier == 0:
                multiplier = decimal.Decimal(1)
            else:
                multiplier *= self.exposureMultiplier
            activeCameras = self.processImages(multiplier)
            print ("Came out with active cams",activeCameras)

        for camera, func in self.camToFunc.items():
            events.unsubscribe(events.NEW_IMAGE % camera.name, func)

        if self.shouldAbort:
            # Don't bother processing images.
            self.cleanup()
            return

        results = []
        for camera in self.cameras:
            results.append(self.makeFit(self.camToAverages[camera]))
        results = numpy.array(results, dtype = numpy.float32)
        results.shape = len(self.cameras), 1, 2, results.shape[-2], results.shape[-1]

        # Construct a header for the image data.
        pixel_size = wx.GetApp().Objectives.GetPixelSize()
        wavelengths = [c.wavelength for c in self.cameras]
        header = cockpit.util.datadoc.makeHeaderFor(results, 
                XYSize = pixel_size, ZSize = 0, 
                wavelengths = wavelengths)

        filehandle = open(self.savePath, 'wb')
        cockpit.util.datadoc.writeMrcHeader(header, filehandle)
        filehandle.write(results)
        filehandle.close()

        self.cleanup()
        

    ## Create the ActionTable needed to run the experiment.
    # \param multiplier Amount to multiply exposure times by.
    # \param activeCameras Cameras that we should still be taking images for.
    def generateActions(self, multiplier, activeCameras):
        table = actionTable.ActionTable()
        curTime = 0
        for cameras, lightTimePairs in self.exposureSettings:
            usedCams = activeCameras.intersection(cameras)
            if usedCams:
                settings = []
                for light, time in lightTimePairs:
                    # We can't actually have a zero exposure time.
                    exposureTime = max(time * multiplier, decimal.Decimal('.1'))
                    settings.append((light, exposureTime))
                for i in range(self.numExposures):
                    curTime = self.expose(curTime, usedCams, settings, table)
        return table


    ## Record an image for the specified camera.
    def recordImage(self, image, camera):
        with self.camToLock[camera]:
            index = self.camToNumImagesReceived[camera]
            self.camToImages[camera][index] = image
            self.camToNumImagesReceived[camera] += 1
            self.lastImageTime = time.time()


    ## This function waits for a certain amount of time to pass after an
    # image is received.
    def waiter(self):
        # Clearly-invalid initial value
        self.lastImageTime = time.time() + 1000
        while time.time() - self.lastImageTime < .25:
            time.sleep(.1)


    ## Examine the images in self.camToImages, discard any that indicate
    # cosmic ray strikes, average the remainder, and put them into 
    # self.camToAverages. Return a set of cameras that had at least 1 valid
    # image.
    def processImages(self, multiplier):
        activeCameras = set()
        for camera, imageData in self.camToImages.items():
            images = imageData[:self.camToNumImagesReceived[camera]]
            if self.shouldPreserveIntermediaryFiles:
                # Save the raw data.
                cockpit.util.datadoc.writeDataAsMrc(images.astype(numpy.uint16),
                        '%s-raw-%s-%d' % (self.savePath, camera.name, multiplier))
                
            stdDev = numpy.std(images)
            median = numpy.median(images)
            print ("For camera",camera,"have median",median,"and std",stdDev)
            threshold = self.cosmicRayThreshold * stdDev + median
            cleanImages = []
            for image in images:
                maxVal = image.max()
                if maxVal < threshold and maxVal < self.maxIntensity:
                    # Verified no cosmic ray strike.
                    cleanImages.append(image)
            print (len(cleanImages),"images are valid")
            if cleanImages:
                self.camToAverages[camera].append(numpy.mean(cleanImages, axis = 0))
                activeCameras.add(camera)
        return activeCameras


    ## Given an array of images, make the offset and gain images.
    # NB assumes that the first image in images is the measured dark offset.
    def makeFit(self, images):
        xVals = map(numpy.mean, images)
        yVals = numpy.array(images)
        imageShape = yVals.shape[1:]
        yVals.shape = len(xVals), numpy.product(imageShape)
        slopes, intercepts = numpy.polyfit(xVals, yVals, 1)
        slopes.shape = imageShape

        return numpy.array([images[0], slopes])



## A consistent name to use to refer to the experiment class itself.
EXPERIMENT_CLASS = OffsetGainCorrectionExperiment
from cockpit.gui.guiUtils import FLOATVALIDATOR, INTVALIDATOR

## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):

    def __init__(self, parent, configKey):
        super().__init__(parent=parent)

        self.configKey = configKey
        self.settings = self.loadSettings()
        
        sizer = wx.GridSizer(3, 2, 2, 2)
        ## Maps strings to TextCtrls describing how to configure 
        # correction file experiments.
        self.correctionArgs = {}
        for key, label, helperString, validator in [
                ('correctionNumExposures', 'Number of exposures', 
                    "How many exposures to take for each exposure time.",
                 INTVALIDATOR),
                ('correctionNumCollections', 'Number of collections',
                    "Maximum number of exposure times to collect data for.",
                 INTVALIDATOR),
                ('correctionExposureMultiplier', 'Exposure multiplier',
                    "Multiplicative factor that governs how quickly we increase exposure time for measuring the camera's response.",
                 FLOATVALIDATOR),
                ('correctionMaxIntensity', 'Max intensity',
                    'Any images above this value are discarded; if we complete imaging and no images "survive", then we are done with data collection.',
                 FLOATVALIDATOR),
                ('correctionCosmicRayThreshold', 'Cosmic ray threshold',
                    "If any pixels in an image are more than this many standard deviations from the median, then the image is discarded.",
                 FLOATVALIDATOR)]:
            control = guiUtils.addLabeledInput(self, sizer, 
                label = label, defaultValue = self.settings[key],
                helperString = helperString)
            control.SetValidator(validator)
            self.correctionArgs[key] = control
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        control = wx.CheckBox(self, label = 'Preserve intermediary files')
        control.SetValue(self.settings['correctionShouldPreserveIntermediaryFiles'])
        rowSizer.Add(control)
        guiUtils.addHelperString(self, rowSizer, 
                "Keep the raw data in addition to the averaged files.")
        self.correctionArgs['correctionShouldPreserveIntermediaryFiles'] = control
        sizer.Add(rowSizer)
        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['numExposures'] = guiUtils.tryParseNum(self.correctionArgs['correctionNumExposures'])
        params['numCollections'] = guiUtils.tryParseNum(self.correctionArgs['correctionNumCollections'])
        params['exposureMultiplier'] = guiUtils.tryParseNum(self.correctionArgs['correctionExposureMultiplier'], float)
        params['maxIntensity'] = guiUtils.tryParseNum(self.correctionArgs['correctionMaxIntensity'])
        params['cosmicRayThreshold'] = guiUtils.tryParseNum(self.correctionArgs['correctionCosmicRayThreshold'], float)
        params['shouldPreserveIntermediaryFiles'] = self.correctionArgs['correctionShouldPreserveIntermediaryFiles'].GetValue()
        return params


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        return cockpit.util.userConfig.getValue(
                self.configKey + 'offsetGainExperimentSettings',
                default = {
                    'correctionCosmicRayThreshold': '10',
                    'correctionExposureMultiplier': '2',
                    'correctionMaxIntensity': '5000',
                    'correctionNumCollections': '5',
                    'correctionNumExposures': '250',
                    'correctionShouldPreserveIntermediaryFiles': False,
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {(key, c.GetValue()) for key, c in self.correctionArgs.items()}


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        cockpit.util.userConfig.setValue(
                self.configKey + 'offsetGainExperimentSettings',
                settings)
