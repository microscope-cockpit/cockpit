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

from cockpit import depot
from cockpit.experiment import experiment

import time


## Immediate-mode experiments are Experiments which perform actions via the
# standard cockpit interactions (e.g. using interfaces.imager.takeImage())
# instead of by generating an ActionTable. As a result, they are easier to
# write, but may not benefit from speed enhancements that the ActionTable
# approach allows.
class ImmediateModeExperiment(experiment.Experiment):
    ## We need to provide enough information here to fill in certain important
    # values in the header. Specifically, we need to know how many images
    # per rep, and how many reps. We would also like to know the Z pixel
    # size (i.e. the distance between images in a 3D volume), if applicable.
    # And of course we need the save path for the file (or else no data will
    # be recorded). Optionally, additional metadata can be supplied.
    def __init__(self, numReps, repDuration, imagesPerRep, sliceHeight = 0,
            metadata = '', savePath = ''):
        super().__init__(numReps, repDuration,
                None, 0, 0, sliceHeight, {},
                metadata = metadata, savePath = savePath)
        # Number of images to be collected per camera per rep.
        self.imagesPerRep = imagesPerRep

        # We didn't pass a proper exposureSettings value when calling
        # the Experiment constructor so we must fix the cameras and
        # lights attributes, as well as related attributes, ourselves.

        ## List of cameras. Assume our cameras are all active cameras.
        self.cameras = []
        for cam in depot.getHandlersOfType(depot.CAMERA):
            if cam.getIsEnabled():
                self.cameras.append(cam)

        ## List of light sources. Assume our lights are all active lights.
        self.lights = []
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            if light.getIsEnabled():
                self.lights.append(light)

        self.allHandlers += self.cameras + self.lights

        self.lightToExposureTime = {l: set() for l in self.lights}
        self.cameraToIsReady = {c: True for c in self.cameras}
        self.cameraToImageCount = {c: 0 for c in self.cameras}
        self.cameraToIgnoredImageIndices = {c: set() for c in self.cameras}


    def prepareHandlers(self):
        """Unlike with normal experiments, we don't prep handlers."""
        pass

    def createValidActionTable(self):
        pass

    ## This experiment will generate images, which need to be saved.
    ## Assume we use all active cameras and light sources.
    def run(self):
        self.cameraToImageCount = {c: self.imagesPerRep for c in self.cameras}
        return super().run()


    ## Run the experiment. Return True if it was successful. This will call
    # self.executeRep() iteratively, taking care of the time to pass between
    # reps for you.
    def execute(self):
        for i in range(self.numReps):
            if self.shouldAbort:
                break
            startTime = time.time()
            self.executeRep(i)
            endTime = time.time()
            waitTime = self.repDuration - (endTime - startTime)
            time.sleep(max(0, waitTime))


    ## Execute one rep of the experiment. Override this function to perform
    # your experiment logic.
    # \param repNum The number of the rep (e.g. 0 = first rep, 1 = second
    #        rep, etc.)
    def executeRep(self, repNum):
        raise RuntimeError(("Immediate-mode experiment %s " % self) +
                "didn't implement its executeRep function.")
