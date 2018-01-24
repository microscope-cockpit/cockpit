from . import dataSaver
import depot
import events
from . import experiment
import gui.guiUtils
import interfaces.stageMover
import util.logger

import gc
import os
import threading
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
        ## Number of images to be collected per camera per rep.
        self.imagesPerRep = imagesPerRep
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
        experiment.Experiment.__init__(self, numReps, repDuration, 
                None, 0, 0, sliceHeight, self.cameras, self.lights, {}, 
                metadata = metadata, savePath = savePath)


    ## Run the experiment. Unlike with normal experiments, we don't prep 
    # handlers, and our DataSaver setup is a bit different. We still spin
    # off saving and execution into separate threads.
    def run(self):
        # Check if the user is set to save to an already-existing file.
        if self.savePath and os.path.exists(self.savePath):
            if not gui.guiUtils.getUserPermission(
                    ("The file:\n%s\nalready exists. " % self.savePath) +
                    "Are you sure you want to overwrite it?"):
                return
        
        # For debugging purposes, this could still be handy.
        experiment.lastExperiment = self

        runThread = threading.Thread(target = self.execute)
        saver = None
        saveThread = None
        if self.savePath and self.imagesPerRep:
            # This experiment will generate images, which need to be saved.
            # Assume we use all active cameras and light sources.
            camToImageCount = dict([(cam, self.imagesPerRep) for cam in self.cameras])
            saver = dataSaver.DataSaver(self.cameras, self.numReps, 
                    camToImageCount, self.cameraToIgnoredImageIndices, 
                    runThread, self.savePath,
                    self.sliceHeight, self.generateTitles())
            saver.startCollecting()
            saveThread = threading.Thread(target = saver.executeAndSave)
            saveThread.start()
            experiment.generatedFilenames.append(saver.getFilenames())
            
        runThread.start()
        # Start up a thread to clean up after the experiment finishes.
        threading.Thread(target = self.cleanup, args = [runThread, saveThread]).start()


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

