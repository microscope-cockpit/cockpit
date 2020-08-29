#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
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


from cockpit.experiment import dataSaver
from cockpit import depot
from cockpit import events
from cockpit.gui import guiUtils

import cockpit.handlers.camera
import cockpit.interfaces.stageMover
import cockpit.util.logger

import decimal
import gc
import os
import threading
import time
import wx


## Purely for debugging purposes, a copy of the last Experiment that was
# executed.
lastExperiment = None

## A track of files generated in previous experiments, so they can be
# viewed in the UI. A list of lists, since each experiment can generate
# multiple files.
generatedFilenames = []

def isRunning():
    """Is an experiment running?
    """
    if lastExperiment is None:
        return False
    else:
        return lastExperiment.is_running()


## This class is the root class for generating and running experiments.

# You should make a subclass of this class to implement a specific experiment
# type.
class Experiment:
    ## This constructor accepts certain parameters that will be shared
    # by all experiment types.
    # \param numReps Number of repetitions of the experiment to perform.
    # \param repDuration Amount of time to spend on each repetition, or

    #        0 to spend as little as possible. In seconds.
    # \param zPositioner StagePositioner handler to use to move in Z.
    # \param altBottom Altitude of the stage at the bottom of the stack.
    # \param zHeight Total height of the stack.
    # \param sliceHeight Distance between slices in the stack.
    # \param exposureSettings List of ([cameras], [(light, exposure time)])
    #        tuples describing how to take images.
    # \param otherHandlers List of miscellaneous handlers that are involved in
    #        the experiment.
    # \param metadata String of extra metadata to insert into the "titles"

    #        section of the saved file.
    # \param savePath Path to save image data to. If this isn't provided then
    #        no data will be saved.
    # *Altitudes* refer to the net position of the Z stage, and are used
    # by the stagemover.
    # *z* values refer to the position of the zPositioner specified in the args.
    def __init__(self, numReps, repDuration,
            zPositioner, altBottom, zHeight, sliceHeight,
            exposureSettings, otherHandlers = [],
            metadata = '', savePath = ''):
        self.numReps = numReps
        self.repDuration = repDuration
        self.zPositioner = zPositioner
        self.altBottom = altBottom
        self.zHeight = zHeight
        self.sliceHeight = sliceHeight
        self.exposureSettings = exposureSettings

        self.cameras = []
        self.lights = []
        for cameras, light_times in exposureSettings:
            self.cameras.extend(cameras)
            self.lights.extend([light for light, time in light_times])

        self.otherHandlers = list(otherHandlers)
        self.metadata = metadata
        self.savePath = savePath

        self._run_thread = None

        # Check for save paths that don't actually have a final filename
        # (i.e. just point to a directory); those aren't valid.
        if not os.path.basename(self.savePath):
            self.savePath = ''

        ## List of all handlers we care about, so we can conveniently set them
        # up.
        self.allHandlers = self.cameras + self.lights + self.otherHandlers
        if self.zPositioner is not None:
            # It may be None in some special experiments that don't do Z
            # stacks.
            self.allHandlers.append(self.zPositioner)
        # Ensure all handlers are experiment-eligible.
        for handler in self.allHandlers:
            if not handler.getIsEligibleForExperiments():
                raise RuntimeError("Handler [%s] is not usable in experiments."
                                   % handler.name)

        ## Maps camera handlers to their minimum time between exposures.
        # Must be populated after exposure time has been set on camera.
        self.cameraToReadoutTime = {}
        ## Maps cameras to whether or not they need to be blanked before they

        # next take an image (because they expose continuously and other

        # cameras have taken images while they were waiting).

        self.cameraToIsReady = {c: True for c in self.cameras}
        ## Maps camera handlers to how many images we'll be taking with that
        # camera.
        self.cameraToImageCount = {c: 0 for c in self.cameras}
        ## Maps camera handlers to indices of which images we will be ignoring
        # from them.
        self.cameraToIgnoredImageIndices = {c: set() for c in self.cameras}

        ## Whether or not we should stop the experiment at the next opportunity.
        self.shouldAbort = False
        events.subscribe(events.USER_ABORT, self.onAbort)

        ## Resultant Z altitude prior to execution, used to restore position.
        self.initialAltitude = None

        ## Baseline position of the zPositioner, used as offset in Z stacks
        self.zStart = None

        ## Maps light sources to sets of exposure times used. This is helpful
        # when setting the "titles" in the MRC header.
        self.lightToExposureTime = {l: set() for l in self.lights}

    ## Cancel the experiment, if it's running.
    def onAbort(self):
        self.shouldAbort = True

    ## Run the experiment. We spin off the actual execution and cleanup
    # into separate threads.
    def run(self):
        # Returns True to close config dialog box, False or None otherwise.
        # Check if the user is set to save to an already-existing file.
        if self.savePath and os.path.exists(self.savePath):
            if not guiUtils.getUserPermission(
                    ("The file:\n%s\nalready exists. " % self.savePath) +
                    "Are you sure you want to overwrite it?"):
                return False

        global lastExperiment
        lastExperiment = self
        self.sanityCheckEnvironment()
        self.prepareHandlers()

        self.cameraToReadoutTime = {c: c.getTimeBetweenExposures(isExact = True)
                                    for c in self.cameras}
        for camera, readTime in self.cameraToReadoutTime.items():
            if type(readTime) is not decimal.Decimal:
                raise RuntimeError("Camera %s did not provide an exact (decimal.Decimal) readout time"
                                   % camera.name)

        # Indicate any frame transfer cameras for reset at start of table.
        for camera in self.cameras:
            if camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_AFTER:
                self.cameraToIsReady[camera] = False

        self.createValidActionTable()
        if self.numReps > 1 and self.repDuration < self.table.lastActionTime / 1000:
            warning = "Repeat duration is less than the time required to run " \
                      "one repeat. Choose:" \
                      "\n    'OK' to run repeats as fast as possible;" \
                      "\n    'Cancel' to go back and change parameters."
            if not guiUtils.getUserPermission(warning):
                return False


        # ToDo: check duration of action table against timelapse settings
        # display appropriate warnings.
        self.lastMinuteActions()

        self._run_thread = threading.Thread(target=self.execute,
                                            name="Experiment-execute")
        self._run_thread.start()

        saveThread = None
        if self.savePath and max(self.cameraToImageCount.values()):

            cameraToExcitation = {c: 0.0 for c in self.cameras}
            for cameras, lightTimePairs in self.exposureSettings:
                ## If there's multiple light sources for the same
                ## camera pick the one with highest wavelength.  Main
                ## case of multiple light sources is single molecule
                ## localisation where a lower wavelength is doing the
                ## pumping while but excitation for fluorescence is
                ## with the higher wavelength.
                if lightTimePairs:
                    max_wavelength = max([l.wavelength for l,t in lightTimePairs])
                else:
                    max_wavelength = 0.0
                for camera in cameras:
                    if camera not in self.cameras:
                        continue
                    cameraToExcitation[camera] = max(cameraToExcitation[camera],
                                                     max_wavelength)

            saver = dataSaver.DataSaver(self.cameras, self.numReps,
                                        self.cameraToImageCount,
                                        self.cameraToIgnoredImageIndices,
                                        self._run_thread, self.savePath,
                                        self.sliceHeight, self.generateTitles(),
                                        cameraToExcitation)
            saver.startCollecting()
            saveThread = threading.Thread(target=saver.executeAndSave,
                                          name="Experiment-execute-save")
            saveThread.start()
            generatedFilenames.append(saver.getFilenames())

        cleanup_thread = threading.Thread(target=self.cleanup,
                                          args=[self._run_thread, saveThread],
                                          name="Experiment-cleanup")
        cleanup_thread.start()
        return True

    ## Create an ActionTable by calling self.generateActions, and give our
    # Devices a chance to sign off on it.
    def createValidActionTable(self):
        self.table = self.generateActions()
        self.table.sort()
        self.examineActions()
        self.table.sort()
        self.table.enforcePositiveTimepoints()

    ## Perform any necessary sanity checks to ensure that the environment is
    # set up properly. Raise an exception if anything is wrong.
    def sanityCheckEnvironment(self):
        pass

    ## Prepare all of the handlers needed in the experiment so that they're
    # in the correct mode.
    def prepareHandlers(self):
        # Store the pre-experiment altitude.
        self.initialAltitude = cockpit.interfaces.stageMover.getPosition()[-1]
        # Ensure that we're the only ones moving things around.
        cockpit.interfaces.stageMover.waitForStop()
        # TODO: Handling multiple movers on an axis is broken. Do not proceed if
        # anything but the innermost Z mover is selected. Needs a proper fix.
        if (cockpit.interfaces.stageMover.mover.curHandlerIndex
            < len(depot.getSortedStageMovers()[2])-1):
            wx.MessageBox("Wrong axis mover selected.")
            raise Exception("Wrong axis mover selected.")
        # Prepare our position.
        cockpit.interfaces.stageMover.goToZ(self.altBottom, shouldBlock = True)
        self.zStart = cockpit.interfaces.stageMover.getAllPositions()[-1][-1]
        events.publish(events.PREPARE_FOR_EXPERIMENT, self)
        # Prepare cameras.
        for camera in self.cameras:
            # We set the expsoure time here. This needs to be set before
            # the action table is generated, since the action table
            # uses camera.getExposureTime to figure out timings.
            exposureTime = float(self.getExposureTimeForCamera(camera))
            camera.setExposureTime(exposureTime)

    ## Allow devices to examine the ActionTable we will be running, and modify
    # it if necessary.
    def examineActions(self):
        for handler in depot.getHandlersOfType(depot.EXECUTOR):
            handler.examineActions(self.table)

    ## Do any last-minute actions immediately before starting the experiment.
    # Return False if anything goes wrong.
    def lastMinuteActions(self):
        pass

    ## Generate an ActionTable of events to perform during the experiment.
    # Return the ActionTable instance.
    def generateActions(self):
        return None

    ## Run the experiment. Return True if it was successful.
    def execute(self):
        cockpit.util.logger.log.info("Experiment.execute started.")
        # Iteratively find the ExperimentExecutor that can tackle the largest
        # portion of self.table, have them run it, and wait for them to finish.
        executors = depot.getHandlersOfType(depot.EXECUTOR)
        self.shouldAbort = False
        for rep in range(self.numReps):
            startTime = time.time()
            repDuration = None
            curIndex = 0
            shouldStop = False
            # Need to track delay introduced by dropping back to software timing.
            delay = 0.
            while curIndex < len(self.table):
                if curIndex > 0:
                    # Update the delay
                    nextTime = delay + startTime + float(self.table[curIndex][0])/1000.
                    delay += max(0, time.time() - nextTime)

                if self.shouldAbort:
                    cockpit.util.logger.log.error("Cancelling on rep %d after %d actions due to user abort" % (rep, curIndex))
                    break
                best = None
                bestLen = 0
                for executor in executors:
                    numLines = executor.getNumRunnableLines(self.table, curIndex)
                    if best is None or numLines > bestLen:
                        best = executor
                        bestLen = numLines
                numReps = 1
                if bestLen == len(self.table):
                    # This executor can handle the entire experiment, so we
                    # should tell them to handle the repeats as well.
                    numReps = self.numReps
                    shouldStop = True
                    # Expand from seconds to milliseconds
                    repDuration = self.repDuration * 1000

                if bestLen == 0:
                    # No executor can run this line. See if we can fall back to software.
                    fn = None
                    t, h, action = self.table[curIndex]
                    if h.deviceType == depot.CAMERA and 'softTrigger' in h.callbacks:
                        fn = lambda: h.callbacks['softTrigger']()
                    elif h.deviceType == depot.STAGE_POSITIONER:
                        fn = lambda: h.moveAbsolute(action)

                    if fn is None:
                        raise RuntimeError("Found a line that no executor could handle: %s" % str(self.table.actions[curIndex]))
                    # Wait until this action is due.
                    if curIndex > 0:
                        timeToNext = delay + startTime + float(self.table[curIndex][0]) / 1000. - time.time()
                        time.sleep(max(0,timeToNext))
                    fn()
                    curIndex += 1
                else:
                    # Don't resume execution too early.
                    # TODO: would be better to pass a 'do not start before' argument
                    # to the handler, so any work it has to do does not add further
                    # delays.
                    if curIndex > 0:
                        timeToNext = delay + startTime + float(self.table[curIndex][0]) / 1000. - time.time()
                        time.sleep(max(0,timeToNext))

                    events.executeAndWaitFor(events.EXPERIMENT_EXECUTION,
                            best.executeTable, self.table, curIndex,
                            curIndex + bestLen, numReps, repDuration)
                    curIndex += bestLen

            if shouldStop:
                # All reps handled by an executor.
                cockpit.util.logger.log.debug("Stopping now at %.2f" % time.time())
                break
            # Wait for the end of the rep.
            if rep != self.numReps - 1:
                waitTime = self.repDuration - (time.time() - startTime)
                time.sleep(max(0, waitTime))
        ## TODO: figure out how long we should wait for the last captures to complete.
        # For now, wait 1s.
        time.sleep(1.)
        cockpit.util.logger.log.info("Experiment.execute completed.")
        return True

    ## Wait for the provided thread(s) to finish, then clean up our handlers.
    def cleanup(self, runThread = None, saveThread = None):
        if runThread is not None:
            runThread.join()
        if saveThread is not None and saveThread.isAlive():
            events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                           'Waiting for saving to complete')
            saveThread.join()
        for handler in self.allHandlers:
            handler.cleanupAfterExperiment()
        events.publish(events.CLEANUP_AFTER_EXPERIMENT)
        if self.initialAltitude is not None:
            # Restore our initial altitude.
            cockpit.interfaces.stageMover.goToZ(self.initialAltitude, shouldBlock = True)
        events.publish(events.EXPERIMENT_COMPLETE)
        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting', '')
        # Ensure the saveThread's memory, which includes all the images
        # collected thus far, is garbage collected. Otherwise memory tends
        # to pile up and then the GC has more work to do, which can interfere
        # with future experiments.
        gc.collect()

    ## Generate the "titles" that provide extra miscellaneous information
    # about the experiment. These are part of the MRC file format spec:
    # http://msg.ucsf.edu/IVE/IVE4_HTML/IM_ref2.html
    # There can be up to 10 titles and they can have up to 80 characters each.
    # We group them by device type.
    def generateTitles(self):
        typeToHandlers = {}
        # Include light filters for our active lights, even though they aren't
        # a part of self.allHandlers.
        typeToHandlers[depot.LIGHT_FILTER] = []
        filters = depot.getHandlersOfType(depot.LIGHT_FILTER)
        for light in self.lights:
            wavelength = light.getWavelength()
            for filterHandler in filters:
                if light in filterHandler.lights:
                    typeToHandlers[depot.LIGHT_FILTER].append(filterHandler)

        for handler in self.allHandlers:
            # We don't care about stage positioners because we always include
            # the complete stage position anyway.
            if handler.deviceType != depot.STAGE_POSITIONER:
                if handler.deviceType not in typeToHandlers:
                    typeToHandlers[handler.deviceType] = []
                typeToHandlers[handler.deviceType].append(handler)
        titles = [
                "Date & time: %s; pos: %s" % (
                    time.strftime('%Y/%m/%d %H:%M:%S'),
                    str(['%.2f' % p for p in (cockpit.interfaces.stageMover.getPosition())])
                )
        ]
        # Append the metadata we were given to start.
        for i in range(0, len(self.metadata) + 80, 80):
            substring = self.metadata[i * 80 : (i + 1) * 80]
            if substring:
                titles.append(substring)

        for deviceType, handlers in typeToHandlers.items():
            handlers = sorted(handlers, key = lambda a: a.name)
            entries = []
            for handler in handlers:
                text = handler.getSavefileInfo()
                if handler in self.lightToExposureTime and self.lightToExposureTime[handler]:
                    text += ': ' + ','.join(["%.3fms" % t for t in sorted(self.lightToExposureTime[handler]) ])
                    # Record the exposure duration(s) of the light source.
                    # find associated power entries (if they have them)
                    
                    for hand in depot.getHandlersInGroup(handler.groupName):
                        if hand.deviceType == depot.LIGHT_POWER:
                            text += " %3.3f mW" % hand.lastPower
                if text:
                    entries.append(text)
            if entries:
                entry = "[%s: %s]" % (deviceType, ';'.join(entries))
                while len(entry) > 80:
                    # Must split it across lines.

                    # \todo For now doing this in an optimally-space-saving
                    # method that will result in ugly titles since we split
                    # lines in the middle of a word.
                    titles.append(entry[:80])
                    entry = entry[80:]
                titles.append(entry)
        if len(titles) > 10:
            raise RuntimeError("Have too much miscellaneous information to fit into the \"titles\" section of the MRC file (max 10 lines). Lines are:\n%s" % "\n".join(titles))
        return titles

    ## Add an exposure to the provided ActionTable. We're provided with the
    # cameras and lights to use for the exposure, as well as how long to
    # expose each light for and when we're allowed to start. We need to
    # enforce that all of the cameras are ready to go before we trigger them.
    # We also need to enforce that any frame-transer cameras have not seen any
    # light since the last time they were blanked.
    # \param lightTimePairs List of (light, exposure time) tuples

    #        describing how long to expose each light for.

    # \return The time at which all exposures are complete.
    def expose(self, curTime, cameras, lightTimePairs, table):
        # First, determine which cameras are not ready to be exposed, because
        # they may have seen light they weren't supposed to see (due to

        # bleedthrough from other cameras' exposures). These need
        # to be triggered (and we need to record that we want to throw away
        # those images) before we can proceed with the real exposure.
        camsToReset = set()
        for camera in cameras:
            if not self.cameraToIsReady[camera]:
                camsToReset.add(camera)
        if camsToReset:
            curTime = self.resetCams(curTime, camsToReset, table)
        # Figure out when we can start the exposure, based on the cameras
        # involved: their exposure modes, readout times, and last trigger
        # times determine how soon we can next trigger them (see
        # getTimeWhenCameraCanExpose() for more information).
        exposureStartTime = curTime
        # Adjust the exposure start based on when the cameras are ready.
        for camera in cameras:
            camExposureReadyTime = self.getTimeWhenCameraCanExpose(table, camera)
            exposureStartTime = max(exposureStartTime, camExposureReadyTime)

        # Determine the maximum exposure time, which depends on our light
        # sources as well as how long we have to wait for the cameras to be
        # ready to be triggered.
        maxExposureTime = 0
        if lightTimePairs:
            maxExposureTime = max(lightTimePairs, key = lambda a: a[1])[1]
        # Check cameras to see if they have minimum exposure times; take them
        # into account for when the exposure can end. Additionally, if they
        # are frame-transfer cameras, then we need to adjust maxExposureTime
        # to ensure that our triggering of the camera does not come too soon
        # (while it is still reading out the previous frame).

        for camera in cameras:
            maxExposureTime = max(maxExposureTime,
                    camera.getMinExposureTime(isExact = True))
            if camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_AFTER:
                nextReadyTime = self.getTimeWhenCameraCanExpose(table, camera)
                # Ensure camera is exposing for long enough to finish reading
                # out the last frame.
                maxExposureTime = max(maxExposureTime,
                        nextReadyTime - exposureStartTime)

        # Open the shutters for the specified exposure times, centered within
        # the max exposure time.
        # Note that a None value here means the user wanted to expose the
        # cameras without any special light.
        exposureEndTime = exposureStartTime + maxExposureTime
        for light, exposureTime, in lightTimePairs:
            if light is not None and light.name != 'ambient': # i.e. not ambient light
                # Center the light exposure.
                timeSlop = maxExposureTime - exposureTime
                offset = timeSlop / 2
                table.addAction(exposureEndTime - exposureTime - offset, light, True)
                table.addAction(exposureEndTime - offset, light, False)
            # Record this exposure time.
            if exposureTime not in self.lightToExposureTime[light]:
                self.lightToExposureTime[light].add(exposureTime)

        # Trigger the cameras. Keep track of which cameras we *aren't* using
        # here; if they are continuous-exposure cameras, then they may have
        # seen light that they shouldn't have, and need to be invalidated.

        usedCams = set()
        for camera in cameras:
            usedCams.add(camera)
            mode = camera.getExposureMode()
            if mode == cockpit.handlers.camera.TRIGGER_AFTER:
                table.addToggle(exposureEndTime, camera)
            elif mode == cockpit.handlers.camera.TRIGGER_DURATION:
                table.addAction(exposureStartTime, camera, True)
                table.addAction(exposureEndTime, camera, False)
            elif mode == cockpit.handlers.camera.TRIGGER_DURATION_PSEUDOGLOBAL:
                # We added some security time to the readout time that
                # we have to remove now
                cameraExposureStartTime = (exposureStartTime
                                           - self.cameraToReadoutTime[camera]
                                           - decimal.Decimal(0.005))
                table.addAction(cameraExposureStartTime, camera, True)
                table.addAction(exposureEndTime, camera, False)
            elif mode == cockpit.handlers.camera.TRIGGER_BEFORE:
                table.addToggle(exposureStartTime, camera)
            elif mode == cockpit.handlers.camera.TRIGGER_SOFT:
                table.addAction(exposureStartTime, camera, True)
            else:
                raise Exception ('%s has no trigger mode set.' % camera)
            self.cameraToImageCount[camera] += 1
        for camera in self.cameras:
            if (camera not in usedCams and
                camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_AFTER):
                # Camera is a continuous-exposure/frame-transfer camera
                # and therefore saw light it shouldn't have; invalidate it.
                self.cameraToIsReady[camera] = False

        return exposureEndTime

    ## Given a set of cameras and a time, trigger the cameras and record that
    # we want to throw away the resulting image. This blanks the camera
    # sensors so they don't record light that we don't care about.
    def resetCams(self, curTime, cameras, table):
        resetEndTime = curTime
        for camera in cameras:
            exposureStart = max(curTime, self.getTimeWhenCameraCanExpose(table, camera))
            # Cameras that have a pre-set exposure time can only use that
            # exposure time for clearing the sensor, hence why we take the
            # maximum of the min exposure time and the current exposure time.
            # \todo Is it possible for getExposureTime() to be less than
            # getMinExposureTime()? That would be a bug, right?
            minExposureTime = max(decimal.Decimal('.1'),
                                  camera.getMinExposureTime(isExact = True),
                                  camera.getExposureTime(isExact = True))
            exposureMode = camera.getExposureMode()
            if exposureMode == cockpit.handlers.camera.TRIGGER_AFTER:
                table.addToggle(exposureStart + minExposureTime, camera)
            elif exposureMode == cockpit.handlers.camera.TRIGGER_DURATION:
                table.addAction(exposureStart, camera, True)
                table.addAction(exposureStart + minExposureTime, camera, False)
            else: # TRIGGER_BEFORE case
                table.addToggle(exposureStart, camera)
            resetEndTime = max(resetEndTime, exposureStart + minExposureTime)
            self.cameraToImageCount[camera] += 1
            self.cameraToIgnoredImageIndices[camera].add(self.cameraToImageCount[camera])
            self.cameraToIsReady[camera] = True
        return resetEndTime + decimal.Decimal('1e-6')

    ## Given a camera handle, return the next time that it will be safe
    # to start an exposure with that camera, based on its last trigger time,
    # its readout time, and its exposure mode:
    # - For TRIGGER_AFTER cameras (i.e. frame transfer cameras), the
    #   exposure starts immediately after the last trigger event for
    #   the camera, but the next trigger time may be postponed to ensure
    #   the camera is ready to readout at the end of the exposure.
    # - For TRIGGER_DURATION cameras (i.e. external exposure), the
    #   camera must wait (camera readout time) after the last trigger
    #   event before it can be triggered again.
    # - For TRIGGER_BEFORE cameras (non-frame-transfer external trigger),
    #   the camera must wait (camera readout time + camera exposure time)
    #   after the last trigger event before it can be triggered again.
    def getTimeWhenCameraCanExpose(self, table, camera):
        lastUseTime, action = table.getLastActionFor(camera)
        if lastUseTime is None:
            # No actions yet; assume camera is ready at the start of the
            # experiment.
            return 0

        nextUseTime = lastUseTime
        if camera.getExposureMode() == cockpit.handlers.camera.TRIGGER_BEFORE:
            # The camera actually finished exposing (and started reading
            # out) some time after lastUseTime, depending on its declared
            # exposure time.
            nextUseTime += camera.getExposureTime(isExact = True)
        nextUseTime += self.cameraToReadoutTime[camera] + decimal.Decimal(0.1)
        return nextUseTime

    ## Return a calculated exposure time for the specified camera handler,
    # based on our exposure settings.
    def getExposureTimeForCamera(self, camera):
        exposureTime = 0
        for cameras, lightTimePairs in self.exposureSettings:
            if camera in cameras and lightTimePairs:
                exposureTime = max(exposureTime, max(lightTimePairs, key = lambda a: a[1])[1])
        return exposureTime

    def is_running(self):
        """Is this experiment running?
        """
        if self._run_thread is None:
            return False
        else:
            return self._run_thread.is_alive()


## Return a list of the files generated by the most recent experiment.
def getLastFilenames():
    if generatedFilenames:
        return generatedFilenames[-1]
    return None
