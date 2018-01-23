import depot
import events
import immediateMode
import interfaces.imager
import interfaces.stageMover

import devices.lights

import numpy
import time



## This class serves as an example of how to run an immediate-mode
# experiment. Make a copy of this file, and modify it to have the logic
# you want. To run it (supposing that your copy is in
# experiment/myExperiment.py), do this in the Python shell in the Cockpit:
# >>> import experiment.myExperiment
# >>> runner = experiment.myExperiment.MyExperiment()
# >>> runner.run()
# If you modify the file, then you need to reload it for changes to take
# effect:
# >>> reload(experiment.myExperiment)
class MyExperiment(immediateMode.ImmediateModeExperiment):
    def __init__(self):
        # We need to tell our parent class (the ImmediateModeExperiment)
        # how many reps we'll be doing, how long each rep lasts, how
        # many images we'll be collecting, and the filepath to save the
        # data to. The experiment assumes we're
        # using the currently-active cameras and light sources for setting
        # up the output data file.
        # Here we do 5 reps, with a 4s duration, and 1 image per rep.
        immediateMode.ImmediateModeExperiment.__init__(self,
                numReps = 5, repDuration = 4, imagesPerRep = 1,
                savePath = "out.mrc")


    ## This function is where you will implement the logic to be performed
    # in each rep of the experiment. The parameter is the number of the
    # rep you are executing, starting from 0 (0 = first rep, 1 = second
    # rep, etc.). 
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
        led650 = depot.getHandlerWithName("650 LED")

        # Get a specific light's power control (ditto).
        led650power = depot.getHandlerWithName("650 LED power")

        # Set the output power to use for this light source, when it is active.
        led650power.setPower(2.5)

        # Set this light source to be continually exposing.
        led650.setExposing(True)

        # Wait for some time (1.5 seconds in this case).
        time.sleep(1.5)

        # Set this light source to stop continually exposing.
        led650.setExposing(False)

        # Get another light source.
        laser488 = depot.getHandlerWithName("488 L")

        # Set this light source to be enabled when we take images.
        # Note: for lasers, an AOM in the laser box that acts as a light
        # shutter is automatically adjusted when you enable/disable lights.
        # I don't know how well enabling multiple lasers simultaneously works.
        # Note: lasers, the DIA light source, and the EPI light source, are
        # mutually exclusive as they use different shutters and only one
        # shutter can be active at a time for some unknown reason. 
        laser488.setEnabled(True)

        # Take images, using all current active camera views and light
        # sources; wait for the image (and time of acquisition) from the named
        # camera to be available.
        # Note: The light sources selected automatically use the emission
        # filter you have set in the UI. If multiple lights use the same
        # emission filter, then they will expose simultaneously (if possible).
        # Note: that if you try to wait for an image
        # that will never arrive (e.g. for the wrong camera name) then your
        # script will get stuck at this point.
        # Note: you must have at least one light source enabled for any
        # image to be taken! 
        eventName = 'new image %s' % activeCams[0].name
        image, timestamp = events.executeAndWaitFor(eventName,
                interfaces.imager.takeImage, shouldBlock = True)

        # Get the min, max, median, and standard deviation of the image
        imageMin = image.min()
        imageMax = image.max()
        imageMedian = numpy.median(image)
        imageStd = numpy.std(image)

        print ("Image stats:", imageMin, imageMax, imageMedian, imageStd)

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

        # Get the device responsible for the dichroics and light sources
        lightsDevice = depot.getDevice(devices.lights)
        # Set a new filter/dichroic for the lower turret.
        lightsDevice.setFilter(isFirstFilter = True, label = "2-488 L")
        # Set a new filter/dichroic for the upper turret.
        lightsDevice.setFilter(isFirstFilter = False, label = "6-600bp")
        # Note: you may want to try setting the filter multiple times in a
        # row as the turret doesn't always actually move to the desired
        # position...
