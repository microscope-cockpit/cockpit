#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Thomas Park <thomasparks@outlook.com>
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

"""Does an open-shutter sweep in Z."""

from cockpit.experiment import actionTable
from cockpit.experiment import experiment


## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Open-shutter sweep'


## This class handles open-shutter sweep experiments, where we move the sample
# continuously while exposing.
class OpenShutterSweepExperiment(experiment.Experiment):
    ## Create the ActionTable needed to run the experiment. We simply start
    # an exposure at the bottom of the "stack" and end it at the top.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        for cameras, lightTimePairs in self.exposureSettings:
            # Start the stage at the bottom.
            table.addAction(curTime, self.zPositioner, 0)
            # Ensure our exposure is at least as long as the time needed to 
            # move through the sample.
            motionTime, stabilizationTime = self.zPositioner.getMovementTime(0,
                    self.zHeight)
            # Image the sample.
            curTime = self.expose(curTime, cameras, lightTimePairs, table)

            # End the exposure with the stage at the top.
            table.addAction(curTime, self.zPositioner, self.zHeight)
            curTime += stabilizationTime
            # Move back to the start so we're ready for the next set of cameras
            # or the next rep.
            motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                    self.zHeight, 0)
            curTime += motionTime
            table.addAction(curTime, self.zPositioner, 0)
            # Hold flat for the stabilization time, and any time needed for
            # the cameras to be ready. Only needed if we're doing multiple
            # reps, so we can proceed immediately to the next one.
            cameraReadyTime = 0
            if self.numReps > 1:
                for cameras, lightTimePairs in self.exposureSettings:
                    for camera in cameras:
                        cameraReadyTime = max(cameraReadyTime,
                                self.getTimeWhenCameraCanExpose(table, camera))
                table.addAction(
                        max(curTime + stabilizationTime, cameraReadyTime),
                        self.zPositioner, 0)

        return table


    def expose(self, curTime, cameras, lightTimePairs, table):
        return curTime



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = OpenShutterSweepExperiment
