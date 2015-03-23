import actionTable
import depot
import experiment
import gui.guiUtils
import util.datadoc
import util.userConfig

import decimal
import math
import numpy
import os
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Structured Illumination'

## Maps possible collection orders to their ordering (0: angle, 1: phase, 2: z).
COLLECTION_ORDERS = {
        "Angle, Phase, Z": (0, 1, 2),
        "Angle, Z, Phase": (0, 2, 1),
        "Phase, Angle, Z": (1, 0, 2),
        "Phase, Z, Angle": (1, 2, 0),
        "Z, Angle, Phase": (2, 0, 1),
        "Z, Phase, Angle": (2, 1, 0),
}



## This class handles SI experiments.
class SIExperiment(experiment.Experiment):
    ## \param numAngles How many angles to perform -- sometimes we only want
    # to do 1 angle, for example. 
    # \param collectionOrder Key from COLLECTION_ORDERS that indicates what
    #        order we change the angle, phase, and Z step in.
    # \param angleHandler DeviceHandler for the device that handles rotations
    #        of the illumination pattern.
    # \param phaseHandler DeviceHandler for the device that handles phase 
    #        changes in the illumination pattern.
    # \param slmHandler Optionally, both angle and phase can be handled by an
    #        SLM or similar pattern-generating device instead. Each handler
    #        (angle, phase, and slm) will be used if present.
    # \param bleachCompensations A dictionary mapping light handlers to
    #        how much to increase their exposure times on successive angles,
    #        to compensate for bleaching.
    def __init__(self, numAngles, collectionOrder, bleachCompensations,
            angleHandler = None, phaseHandler = None, slmHandler = None,
            *args, **kwargs):
        # Store the collection order in the MRC header.
        metadata = 'SI order: %s' % collectionOrder
        if 'metadata' in kwargs:
            # Augment the existing string.
            kwargs['metadata'] += "; %s" % metadata
        else:
            kwargs['metadata'] = metadata
        experiment.Experiment.__init__(self, *args, **kwargs)
        self.numAngles = numAngles
        self.numPhases = 5
        self.numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        if self.zHeight > 1e-6:
            # Non-2D experiment; tack on an extra image to hit the top of
            # the volume.
            self.numZSlices += 1
        self.collectionOrder = collectionOrder
        self.angleHandler = angleHandler
        self.phaseHandler = phaseHandler
        self.slmHandler = slmHandler
        self.handlerToBleachCompensation = bleachCompensations


    ## Generate a sequence of (angle, phase, Z) positions for SI experiments,
    # based on the order the user specified.
    def genSIPositions(self):
        ordering = COLLECTION_ORDERS[self.collectionOrder]
        maxVals = (self.numAngles, self.numPhases, self.numZSlices)
        for i in xrange(maxVals[ordering[0]]):
            for j in xrange(maxVals[ordering[1]]):
                for k in xrange(maxVals[ordering[2]]):
                    vals = (i, j, k)
                    angle = vals[ordering.index(0)]
                    phase = vals[ordering.index(1)]
                    z = vals[ordering.index(2)]
                    yield (angle, phase, z * self.sliceHeight)


    ## Create the ActionTable needed to run the experiment. We do three 
    # Z-stacks for three different angles, and take five images at each 
    # Z-slice, one for each phase.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        prevAngle, prevZ, prevPhase = None, None, None

        # Set initial angle and phase, if relevant. We assume the SLM (if any)
        # is already showing the correct pattern for the first image set.
        # Increment the time slightly after each "motion" so that actions are well-ordered.
        if self.angleHandler is not None:
            table.addAction(curTime, self.angleHandler, 0)
            curTime += decimal.Decimal('1e-6')
        if self.phaseHandler is not None:
            table.addAction(curTime, self.phaseHandler, 0)
            curTime += decimal.Decimal('1e-6')
        table.addAction(curTime, self.zPositioner, 0)
        curTime += decimal.Decimal('1e-6')
        
        for angle, phase, z in self.genSIPositions():
            delayBeforeImaging = 0
            # Figure out which positions changed. They need to be held flat
            # up until the move, then spend some amount of time moving,
            # then have some time to stabilize. Or, if we have an SLM, then we
            # need to trigger it and then wait for it to stabilize.
            # Ensure we truly are doing this after all exposure events are done.
            curTime = table.getFirstAndLastActionTimes()[1] + decimal.Decimal('1e-6')
            if angle != prevAngle and prevAngle is not None:
                if self.angleHandler is not None:
                    motionTime, stabilizationTime = self.angleHandler.getMovementTime(prevAngle, angle)
                    # Hold flat.
                    table.addAction(curTime, self.angleHandler, prevAngle)
                    # Move to the next position.
                    table.addAction(curTime + motionTime, 
                            self.angleHandler, angle)
                    delayBeforeImaging = max(delayBeforeImaging, 
                            motionTime + stabilizationTime)
                # Advance time slightly so all actions are sorted (e.g. we
                # don't try to change angle and phase in the same timestep).
                curTime += decimal.Decimal('.001')

            if phase != prevPhase and prevPhase is not None:
                if self.phaseHandler is not None:
                    motionTime, stabilizationTime = self.phaseHandler.getMovementTime(prevPhase, phase)
                    # Hold flat.
                    table.addAction(curTime, self.phaseHandler, prevPhase)
                    # Move to the next position.
                    table.addAction(curTime + motionTime, 
                            self.phaseHandler, phase)
                    delayBeforeImaging = max(delayBeforeImaging, 
                            motionTime + stabilizationTime)
                # Advance time slightly so all actions are sorted (e.g. we
                # don't try to change angle and phase in the same timestep).
                curTime += decimal.Decimal('.001')
                
            if z != prevZ:
                if prevZ is not None:
                    motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevZ, z)
                    # Hold flat.
                    table.addAction(curTime, self.zPositioner, prevZ)
                    # Move to the next position.
                    table.addAction(curTime + motionTime, 
                            self.zPositioner, z)
                    delayBeforeImaging = max(delayBeforeImaging, 
                            motionTime + stabilizationTime)
                # Advance time slightly so all actions are sorted (e.g. we
                # don't try to change angle and phase in the same timestep).
                curTime += decimal.Decimal('.001')

            prevAngle = angle
            prevPhase = phase
            prevZ = z

            curTime += delayBeforeImaging
            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, angle, phase, table)
                
        # Hold Z, angle, and phase steady through to the end, then ramp down
        # to 0 to prep for the next experiment.
        table.addAction(curTime, self.zPositioner, prevZ)
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        table.addAction(curTime + motionTime, self.zPositioner, 0)
        finalWaitTime = motionTime + stabilizationTime

        # Ramp down Z
        table.addAction(curTime + finalWaitTime, self.zPositioner, 0)

        if self.angleHandler is not None:
            # Ramp down angle        
            table.addAction(curTime, self.angleHandler, prevAngle)
            motionTime, stabilizationTime = self.angleHandler.getMovementTime(
                    prevAngle, 0)
            table.addAction(curTime + motionTime, self.angleHandler, 0)
            finalWaitTime = max(finalWaitTime, motionTime + stabilizationTime)
        if self.phaseHandler is not None:
            # Ramp down phase
            table.addAction(curTime, self.phaseHandler, prevPhase)
            motionTime, stabilizationTime = self.phaseHandler.getMovementTime(
                    prevAngle, 0)
            table.addAction(curTime + motionTime, self.phaseHandler, 0)
            finalWaitTime = max(finalWaitTime, motionTime + stabilizationTime)
        
        if self.slmHandler is not None:
            # Add a last trigger of the SLM to cycle back to the start.
            table.addAction(curTime, self.slmHandler, 0)
            self.slmHandler.examineActions(table)

        return table


    ## Wrapper around Experiment.expose() that:
    # 1: adjusts exposure times based on the current angle, to compensate for 
    # bleaching;
    # 2: uses an SLM (if available) to optimise SIM for each exposure.    
    def expose(self, curTime, cameras, lightTimePairs, angle, phase, table):
        # new lightTimePairs with exposure times adjusted for bleaching.
        newPairs = []
        # If a SIM pattern puts the 1st-order spots for a given wavelength at 
        # the edge of the back pupil, the 1st-order spots from longer wave-
        # lengths will fall beyond the edge of the pupil. Therefore, we use the 
        # longest wavelength in a given exposure to determine the SIM pattern.
        longestWavelength = 0   
        # Using tExp rather than 'time' to avoid confusion between table event 
        # times and exposure durations.
        for light, tExp in lightTimePairs:
            # SIM wavelength
            longestWavelength = max(longestWavelength, light.wavelength)
            # Bleaching compensation
            tExpNew = tExp * (1 + decimal.Decimal(self.handlerToBleachCompensation[light]) * angle)
            newPairs.append((light, tExpNew))
            # SLM trigger
        if self.slmHandler is not None:
           ## Add SLM event ot set pattern for phase, angle and longestWavelength.
           # The SLM handler will add triggering and settling delays when it 
           # examines the action table by pushing back all subsequent events.
           table.addAction(curTime, self.slmHandler, (angle, phase, longestWavelength))
           # Add a small delay so that the exposure falls after the SLM event.
           curTime += decimal.Decimal('1e-6')
        return experiment.Experiment.expose(self, curTime, cameras, newPairs, table)


    ## As part of cleanup, we have to modify the saved file to have its images
    # be in the order that Priism expects them to be in so that it can
    # reconstruct them correctly. That means converting from our collection
    # order, whatever it may be, to Angle-Z-Phase order.
    def cleanup(self, runThread = None, saveThread = None):
        experiment.Experiment.cleanup(self, runThread, saveThread)
        if self.collectionOrder == "Angle, Z, Phase":
            # Already in order; don't do anything.
            return
        if self.savePath is not None:
            doc = util.datadoc.DataDoc(self.savePath)
            newData = numpy.zeros(doc.imageArray.shape, dtype = doc.imageArray.dtype)
            # Determine how to index into the source dataset. The slowest-
            # changing value has the largest multiplier.
            ordering = COLLECTION_ORDERS[self.collectionOrder]
            tmp = (self.numAngles, self.numPhases, self.numZSlices)
            # Reorder based on ordering.
            tmp = [tmp[i] for i in ordering]
            stepToMultiplier = {}
            for i, index in enumerate(ordering):
                stepToMultiplier[index] = numpy.product(tmp[i + 1:])
            sourceAMult = stepToMultiplier[0]
            sourcePMult = stepToMultiplier[1]
            sourceZMult = stepToMultiplier[2]
            targetAMult = self.numPhases * self.numZSlices
            targetPMult = 1
            targetZMult = self.numPhases
            for angle in xrange(self.numAngles):
                for phase in xrange(self.numPhases):
                    for z in xrange(self.numZSlices):
                        source = angle * sourceAMult + phase * sourcePMult + z * sourceZMult
                        target = angle * targetAMult + phase * targetPMult + z * targetZMult
                        newData[:, :, target] = doc.imageArray[:, :, source]

            # Write the data out.
            # HACK: we're ignoring the extended header here; oh well.
            header = util.datadoc.makeHeaderForShape(newData.shape,
                    dtype = newData.dtype, XYSize = doc.imageHeader.d[0],
                    ZSize = doc.imageHeader.d[2],
                    wavelengths = doc.imageHeader.wave)
            header.title = doc.imageHeader.title            
            del doc
            
            # Write the new data to a new file, then remove the old file
            # and put the new one where it was.
            tempPath = self.savePath + str(os.getpid())
            handle = open(tempPath, 'wb')
            util.datadoc.writeMrcHeader(header, handle)
            handle.write(newData)
            handle.close()
            os.remove(self.savePath)
            os.rename(tempPath, self.savePath)



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = SIExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)

        self.configKey = configKey
        self.allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        self.settings = self.loadSettings()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.shouldOnlyDoOneAngle = wx.CheckBox(self,
                label = "Do only one angle")
        self.shouldOnlyDoOneAngle.SetValue(self.settings['shouldOnlyDoOneAngle'])
        rowSizer.Add(self.shouldOnlyDoOneAngle, 0, wx.ALL, 5)

        text = wx.StaticText(self, -1, "Exposure bleach compensation (%):")
        rowSizer.Add(text, 0, wx.ALL, 5)
        ## Ordered list of bleach compensation percentages.
        self.bleachCompensations, subSizer = gui.guiUtils.makeLightsControls(
                self,
                [str(l.name) for l in self.allLights],
                self.settings['bleachCompensations'])
        rowSizer.Add(subSizer)
        sizer.Add(rowSizer)
        # Now a row for the collection order.
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.siCollectionOrder = gui.guiUtils.addLabeledInput(self,
                rowSizer, label = "Collection order",
                control = wx.Choice(self, choices = sorted(COLLECTION_ORDERS.keys())),
                helperString = "What order to change the angle, phase, and Z step of the experiment. E.g. for \"Angle, Phase, Z\" Angle will change most slowly and Z will change fastest.")
        self.siCollectionOrder.SetSelection(self.settings['siCollectionOrder'])
        sizer.Add(rowSizer)
        self.SetSizerAndFit(sizer)
        

    ## Given a parameters dict (parameter name to value) to hand to the
    # experiment instance, augment them with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['numAngles'] = 3
        if self.shouldOnlyDoOneAngle.GetValue():
            params['numAngles'] = 1
        params['collectionOrder'] = self.siCollectionOrder.GetStringSelection()
        params['angleHandler'] = depot.getHandlerWithName('SI angle')
        params['phaseHandler'] = depot.getHandlerWithName('SI phase')
        params['slmHandler'] = depot.getHandlerWithName('slm executor')
        compensations = {}
        for i, light in enumerate(self.allLights):
            val = gui.guiUtils.tryParseNum(self.bleachCompensations[i], float)
            if val:
                # Convert from percentage to multiplier
                compensations[light] = .01 * float(val)
            else:
                compensations[light] = 0
        params['bleachCompensations'] = compensations
        return params


    ## Load the saved experiment settings, if any.
    def loadSettings(self):
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        result = util.userConfig.getValue(
                self.configKey + 'SIExperimentSettings', 
                default = {
                    'bleachCompensations': ['' for l in self.allLights],
                    'shouldOnlyDoOneAngle': False,
                    'siCollectionOrder': 0,
                }
        )
        if len(result['bleachCompensations']) != len(self.allLights):
            # Number of light sources has changed; invalidate the config.
            result['bleachCompensations'] = ['' for light in self.allLights]
        return result


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'bleachCompensations': [c.GetValue() for c in self.bleachCompensations],
                'shouldOnlyDoOneAngle': self.shouldOnlyDoOneAngle.GetValue(),
                'siCollectionOrder': self.siCollectionOrder.GetSelection(),
        }
    

    ## Save the current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'SIExperimentSettings', settings
        )
