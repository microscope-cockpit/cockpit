from . import actionTable
import decimal
import depot
import events
from . import experiment
import gui.guiUtils
import gui.imageSequenceViewer
import gui.progressDialog
import handlers.camera
from . import offsetGainCorrection
import util.correctNonlinear
import util.datadoc
import util.threads
import util.userConfig

import matplotlib
matplotlib.use('WXAgg')
import matplotlib.backends.backend_wxagg
import matplotlib.figure
import numpy
import threading
import time
import wx

from six import iteritems

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Response map correction file'


## This class collects the data needed to perform response-map correction.
# It takes exposures of some flat illumination source (e.g. 
# a Chroma slide) at varying exposure times, to characterize the response of 
# the cameras to incident light. Structurally this class is very similar to 
# the OffsetGainCorrectionExperiment class.
class ResponseMapExperiment(offsetGainCorrection.OffsetGainCorrectionExperiment):
    ## \param numExposures How many images to take for each exposure time.
    # \param exposureTimes List of exposure times to take images for.
    # \param cosmicRayThreshold If any pixels are more than this many 
    #        standard deviations away from the median of the overall image, then
    #        the image is discarded.
    # \param shouldPreserveIntermediaryFiles If True, then save the raw
    #        data in addition to the averaged files.
    def __init__(self, cameras, lights, exposureSettings, numExposures, 
            savePath, exposureTimes, cosmicRayThreshold,
            shouldPreserveIntermediaryFiles, **kwargs):
        # Fill in some dummy values here for parameters that we don't actually
        # use.
        offsetGainCorrection.OffsetGainCorrectionExperiment.__init__(
                self, cameras, lights, exposureSettings,
                numExposures, savePath, exposureMultiplier = 0, 
                maxIntensity = None, cosmicRayThreshold = cosmicRayThreshold,
                shouldPreserveIntermediaryFiles = shouldPreserveIntermediaryFiles)
        self.numExposures = numExposures
        self.savePath = savePath
        self.exposureTimes = map(decimal.Decimal, exposureTimes)
        self.cosmicRayThreshold = cosmicRayThreshold
        ## List of (exposure time, averaged images, sample raw image) tuples.
        self.timesAndImages = []
        ## Maximum width/height of an image for any camera we use.
        self.maxImageDims = [0, 0]


    ## Very similar to OffsetGainCorrectionExperiment.run() except that we
    # calculate the exposure times to use differently, and have a different
    # stopping condition. We also generate some output at the end to 
    # demonstrate our results.
    @util.threads.callInNewThread
    def run(self):
        # For debugging purposes
        experiment.lastExperiment = self
        
        self.sanityCheckEnvironment()
        self.prepareHandlers()

        self.cameraToReadoutTime = dict([(c, c.getTimeBetweenExposures(isExact = True)) for c in self.cameras])
        for camera, readTime in iteritems(self.cameraToReadoutTime):
            if type(readTime) is not decimal.Decimal:
                raise RuntimeError("Camera %s did not provide an exact (decimal.Decimal) readout time" % camera.name)

        for camera, func in iteritems(self.camToFunc):
            events.subscribe('new image %s' % camera.name, func)
        for exposureTime in self.exposureTimes:
            if self.shouldAbort:
                break
            self.camToImages = {}
            self.camToNumImagesReceived = {}
            self.camToLock = {}
            for camera in self.cameras:
                # Prepare a memory buffer to store images in.
                width, height = camera.getImageSize()
                self.camToImages[camera] = numpy.zeros((self.numExposures, height, width))
                self.camToNumImagesReceived[camera] = 0
                self.camToLock[camera] = threading.Lock()
                # Indicate any frame transfer cameras for reset at start of
                # table.
                if camera.getExposureMode() == handlers.camera.TRIGGER_AFTER:
                    self.cameraToIsReady[camera] = False
                
            self.table = self.generateActions(exposureTime)
            self.table.sort()
            self.examineActions()
            self.table.sort()
            self.table.enforcePositiveTimepoints()
            self.lastMinuteActions()
            self.doneReceivingThread = threading.Thread(target = self.waiter)
            self.doneReceivingThread.start()
            self.execute()
            
            if self.shouldAbort:
                break
            
            # Wait until it's been a short time after the last received image.
            self.doneReceivingThread.join()
            progress = gui.progressDialog.ProgressDialog("Processing images", 
                    "Processing images for exposure time %.4f" % exposureTime,
                    parent = None)
            self.processImages(exposureTime)
            progress.Destroy()

        for camera, func in iteritems(self.camToFunc):
            events.unsubscribe('new image %s' % camera.name, func)

        self.save()
        self.showResults()
        self.cleanup()
        

    ## Save our averaged images together in a single file, with the 
    # exposure time in the extended header.
    def save(self):
        # First, re-order our images into WTZ order (with the Z axis being
        # flat).
        numTimes = len(self.timesAndImages)
        numCams = len(self.timesAndImages[0][1])
        allImages = numpy.zeros((numCams, numTimes, 1, self.maxImageDims[0], self.maxImageDims[1]), dtype = numpy.float32)
        exposureTimes = []
        for timepoint, (exposureTime, images, rawImages) in enumerate(self.timesAndImages):
            for wavelength, image in enumerate(images):
                height, width = image.shape
                allImages[wavelength, timepoint, 0, :height, :width] = image
                exposureTimes.append(exposureTime)
        
        drawer = depot.getHandlersOfType(depot.DRAWER)[0]
        header = util.datadoc.makeHeaderFor(allImages, 
                wavelengths = [cam.wavelength for cam in self.cameras])

        # Number of bytes allocated to the extended header: 4 per image, since
        # we use a 32-bit floating point for the exposure time.
        header.next = 4 * numCams * numTimes
        header.NumFloats = 1
        handle = open(self.savePath, 'wb')
        handle.write(header._array.tostring())
        exposureTimes = numpy.array(exposureTimes, dtype = numpy.float32)
        handle.write(exposureTimes)
        handle.write(allImages)
        handle.close()


    ## Demonstrate our results to the user in a number of ways.
    def showResults(self):
        # First, show plots of the linearity of some of the pixels, before
        # and after correction.
        xVals = numpy.array([d[0] for d in self.timesAndImages])
        averagedImages = numpy.array([d[1] for d in self.timesAndImages])
        rawImages = numpy.array([d[2] for d in self.timesAndImages])
        self.plotPixels(xVals, rawImages, "Pre-corrected pixel linearity survey")
        correctedImages = numpy.empty(rawImages.shape)
        for cam in range(rawImages.shape[1]):
            corrector = util.correctNonlinear.Corrector(xVals, averagedImages[:, cam])
            correctedImages[:, cam] = map(corrector.correct, rawImages[:, cam])
        self.plotPixels(xVals, correctedImages, "Corrected pixel linearity survey")

        # Also show what the images look like before and after correction.
        # This requires reordering the images from (exposure time, cam, Y, X)
        # to (cam, exposure time, 1, Y, X)
        rawImages.shape = list(rawImages.shape) + [1]
        correctedImages.shape = rawImages.shape
        # T, W, Y, X, Z -> W, T, Z, Y, X
        rawImages = rawImages.transpose(1, 0, 4, 2, 3)
        correctedImages = correctedImages.transpose(1, 0, 4, 2, 3)
        # Ensure we have valid datatypes for display.
        rawImages = numpy.float32(rawImages)
        correctedImages = numpy.float32(correctedImages)
        viewer1 = gui.imageSequenceViewer.ImageSequenceViewer(rawImages, 
                "Uncorrected sample images", parent = None)
        viewer2 = gui.imageSequenceViewer.ImageSequenceViewer(correctedImages,
                "Corrected sample images", parent = None)



    ## Given some images, plot a few pixels.
    def plotPixels(self, xVals, images, title):
        figure = matplotlib.figure.Figure((6, 4), dpi = 100, 
                facecolor = (1, 1, 1))
        axes = figure.add_subplot(1, 1, 1)
        axes.set_axis_bgcolor('white')
        axes.set_title(title)
        axes.set_ylabel('Individual pixel value')
        axes.set_xlabel('Exposure time (ms)')

        # Plot pixels from the centers of each quadrant as well as from
        # the center of the image and the average of the image as a whole.
        lines = []
        labels = []
        for cam in range(images.shape[1]):
            camImages = images[:, cam]
            height, width = camImages[0].shape
            cy = height / 2
            cx = width / 2
            for color, xOffset, yOffset in [('r', -1, -1), ('g', -1, 1), 
                    ('b', 1, 1), ('c', 1, -1), ('m', 0, 0)]:
                y = cy + yOffset * height / 4
                x = cx + xOffset * width / 4
                lines.append(axes.plot(xVals, camImages[:, y, x], color))
                labels.append("Pixel at %d, %d for cam %d" % (x, y, cam))
            lines.append(axes.plot(xVals, map(numpy.mean, camImages), 'k'))
            labels.append("Average for cam %d" % cam)
        figure.legend(lines, labels, loc = 'upper left')
        frame = wx.Frame(None, title = "Linearity plot")
        canvas = matplotlib.backends.backend_wxagg.FigureCanvasWxAgg(
                frame, -1, figure)
        canvas.draw()
        # Big enough to be visible, but unlikely to run off the edge of 
        # the screen.
        frame.SetSize((640, 480))
        frame.Show()


    ## Create the ActionTable needed to run the experiment. We basically 
    # ignore the values in self.exposureSettings in favor of the provided
    # exposure time.
    def generateActions(self, exposureTime):
        table = actionTable.ActionTable()
        curTime = 0
        allCams = set(self.cameras)
        for cameras, lightTimePairs in self.exposureSettings:
            usedCams = allCams.intersection(cameras)
            if usedCams:
                settings = []
                for light, time in lightTimePairs:
                    # We can't actually have a zero exposure time, so use
                    # 1ns as a minimum.
                    exposureTime = max(exposureTime, decimal.Decimal('.000001'))
                    settings.append((light, exposureTime))
                for i in range(self.numExposures):
                    curTime = self.expose(curTime, usedCams, settings, table)
        return table


    ## Examine the images in self.camToImages, discard any that indicate
    # cosmic ray strikes or have unusual median intensities, average the
    # remainder, and put them into 
    # self.camToAverages. Return a (possibly empty) set of cameras that had at
    # least 1 valid image.
    def processImages(self, exposureTime):
        activeCameras = set()
        averages = []
        raws = []
        cameras = sorted(self.camToImages.keys())
        for camera in cameras:
            images = self.camToImages[camera][:self.camToNumImagesReceived[camera]]
            # Save the last image, on the assumption that any issue with
            # camera or light variance will have gotten flattened out by that
            # time.
            raws.append(images[-1])
            if self.shouldPreserveIntermediaryFiles:
                # Save the raw data.
                util.datadoc.writeDataAsMrc(images.astype(numpy.uint16),
                        '%s-raw-%s-%04.5fms' % (self.savePath, camera.name, exposureTime))

            # Calculate a threshold for cosmic ray strikes.
            stdDev = numpy.std(images)
            median = numpy.median(images)
            print ("For camera",camera,"have median",median,"and std",stdDev)
            threshold = self.cosmicRayThreshold * stdDev + median
            # To cope with the fact that some images may be improperly
            # exposed, we want to find statistics that are true for most
            # of the images, hence the per-image statistics here.
            medianStd = numpy.median([numpy.std(image) for image in images])
            medianMedian = numpy.median([numpy.median(image) for image in images])
            accumulator = numpy.zeros(images[0].shape, dtype = numpy.float32)
            numCleanImages = 0
            for image in images:
                imageMax = image.max()
                imageMedian = numpy.median(image)
                if imageMax < threshold and abs(imageMedian - medianMedian) < medianStd:
                    # Verified no cosmic ray strike and sensible intensity.
                    accumulator += image
                    numCleanImages += 1

            accumulator /= numCleanImages

            averages.append(accumulator)
            for i in range(2):
                self.maxImageDims[i] = max(self.maxImageDims[i], accumulator.shape[i])
            print (numCleanImages,"images are valid")
        self.timesAndImages.append((exposureTime, averages, raws))




## A consistent name to use to refer to the experiment class itself.
EXPERIMENT_CLASS = ResponseMapExperiment



## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)
        self.configKey = configKey
        sizer = wx.GridSizer(2, 2, 2, 2)
        ## Maps strings to TextCtrls describing how to configure 
        # response curve experiments.
        self.settings = self.loadSettings()
        self.responseArgs = {}
        for key, label, helperString in [
                ('responseMapNumExposures', 'Number of exposures', 
                    "How many exposures to take for each exposure time."),
                ('responseMapExposureTimes', 'Exposure times', 
                    "Comma-separated list of exposure times at which to collect data."),
                ('responseMapCosmicRayThreshold', 
                    'Cosmic ray threshold',
                    "If any pixels in an image are more than this many standard deviations from the median, then the image is discarded.")]:
            control = gui.guiUtils.addLabeledInput(self, sizer, 
                label = label, defaultValue = self.settings[key],
                helperString = helperString)
            self.responseArgs[key] = control
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        control = wx.CheckBox(self, label = 'Preserve intermediary files')
        control.SetValue(self.settings['responseMapShouldPreserveIntermediaryFiles'])
        rowSizer.Add(control)
        gui.guiUtils.addHelperString(self, rowSizer, 
                "Keep the raw data in addition to the averaged files.")
        self.responseArgs['responseMapShouldPreserveIntermediaryFiles'] = control
        sizer.Add(rowSizer)
        self.SetSizerAndFit(sizer)


    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['numExposures'] = gui.guiUtils.tryParseNum(self.responseArgs['responseMapNumExposures'])
        tokens = self.responseArgs['responseMapExposureTimes'].GetValue()
        tokens = tokens.split(',')
        params['exposureTimes'] = map(float, tokens)
        params['cosmicRayThreshold'] = gui.guiUtils.tryParseNum(self.responseArgs['responseMapCosmicRayThreshold'])
        params['shouldPreserveIntermediaryFiles'] = self.responseArgs['responseMapShouldPreserveIntermediaryFiles'].GetValue()
        return params        


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'responseMapExperimentSettings',
                default = {
                    'responseMapCosmicRayThreshold': '10', 
                    'responseMapExposureTimes': '1,2,3,4,5',
                    'responseMapNumExposures': '250',
                    'responseMapShouldPreserveIntermediaryFiles': False,
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return dict([(key, c.GetValue()) for key, c in iteritems(self.responseArgs)])


    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'responseMapExperimentSettings',
                settings)
