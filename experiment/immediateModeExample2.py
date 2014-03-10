import depot
import events
import immediateMode
import interfaces.imager
import interfaces.stageMover
import util.user

import numpy
import os
import time



## This class serves as an example of how to run an immediate-mode
# experiment. Make a copy of this file, and modify it to have the logic
# you want. To run it (supposing that your copy is in
# experiment/myExperiment.py), do this in the Python shell in the Cockpit:
# >>> import experiment.myExperiment
# >>> runner = experiment.myExperiment.MyExperiment()
# >>> runner.run()
# If you make changes to the experiment while the cockpit is running, you will
# need to reload the experiment module for those changes to take effect:
# >>> reload(experiment.myExperiment)
class MyExperiment(immediateMode.ImmediateModeExperiment):
    def __init__(self):
        # We need to tell our parent class (the ImmediateModeExperiment)
        # how many reps we'll be doing, how long each rep lasts, how
        # many images we'll be collecting, and the filepath to save the
        # data to. The experiment assumes we're
        # using the currently-active cameras and light sources for setting
        # up the output data file.
        # Here we do 5 reps, with a 4s duration, and 1 image per rep. The 
        # file will get saved as "out.mrc" in the current user's data 
        # directory.
        savePath = os.path.join(util.user.getUserSaveDir(), "out.mrc")
        print "Saving file to",savePath
        immediateMode.ImmediateModeExperiment.__init__(self,
                numReps = 5, repDuration = 4, imagesPerRep = 1,
                savePath = savePath)


    ## This function is where you will implement the logic to be performed
    # in each rep of the experiment. 
    def executeRep(self, repNum):
        # Get all light sources that the microscope has.
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        # getHandlersOfType returns an unordered set datatype. If we want to
        # index into allLights, we need to convert it to a list first.
        allLights = list(allLights)
        # Print the names of all light sources.
        for light in allLights:
            print light.name
        # Get all power controls for light sources.
        allLightPowers = depot.getHandlersOfType(depot.LIGHT_POWER)
        # Get all light source filters.
        allLightFilters = depot.getHandlersOfType(depot.LIGHT_FILTER)

        # Get all camera handlers that the microscope has, and filter it
        # down to the ones that are currently active.
        allCameras = depot.getHandlersOfType(depot.CAMERA)
        # Create a new empty list.
        activeCams = []
        for camera in allCameras:
            if camera.getIsEnabled():
                # Camera is enabled.
                activeCams.append(camera)

        # Get a specific light.
        deepstar405 = depot.getHandlerWithName("488 Deepstar")

        deepstar405power = depot.getHandlerWithName("488 Deepstar power")

        # Set the output power to use for this light source, when it is active.
        deepstar405power.setPower(15)

        # Get another light source. The "\n" in the name is a newline, which
        # was inserted (when this light source handler was created) to make
        # the light control button look nice. 
        laser488 = depot.getHandlerWithName("488\nlight")

        # Set this light source to be enabled when we take images.
        laser488.setEnabled(True)

        # Take images, using all current active camera views and light
        # sources; wait for the image (and time of acquisition) from the named
        # camera to be available.
        # Note: that if you try to wait for an image
        # that will never arrive (e.g. for the wrong camera name) then your
        # script will get stuck at this point.
        eventName = 'new image %s' % activeCams[0].name
        image, timestamp = events.executeAndWaitFor(eventName,
                interfaces.imager.takeImage, shouldBlock = True)

        # Get the min, max, median, and standard deviation of the image
        imageMin = image.min()
        imageMax = image.max()
        imageMedian = numpy.median(image)
        imageStd = numpy.std(image)

        print "Image stats:", imageMin, imageMax, imageMedian, imageStd

        # Some miscellaneous functions below.

        # Get the current stage position; positions are in microns.
        curX, curY, curZ = interfaces.stageMover.getPosition()
        # Move to a new Z position, and wait until we arrive.
        interfaces.stageMover.goToZ(curZ + 5, shouldBlock = True)
        # Move to a new XY position.
        # Note: the goToXY function expects a "tuple" for the position,
        # hence the extra parentheses (i.e. "goToXY(x, y)" is invalid;
        # "goToXY((x, y))" is correct). 
        interfaces.stageMover.goToXY((curX + 50, curY - 50), shouldBlock = True)

