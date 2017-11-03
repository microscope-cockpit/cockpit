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
import tempfile
import shutil
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Structured Illumination'

## Maps possible collection orders to their ordering (0: angle, 1: phase, 2: z).
COLLECTION_ORDERS = {
#        "Angle, Phase, Z": (0, 1, 2),
#        "Angle, Z, Phase": (0, 2, 1),
#        "Phase, Angle, Z": (1, 0, 2),
#       "Phase, Z, Angle": (1, 2, 0),
        "Z, Angle, Phase": (2, 0, 1),
        "Z, Phase, Angle": (2, 1, 0),
}

def collection_order_tuple(order_str):
    """Return collection order in a tuple of 1 character c-style index.

    A bit more sensible, lower-case, one character, tuple.
    """
    to1char = {
        0 : "a",
        1 : "p",
        2 : "z",
    }
    z_order = [to1char[x] for x in COLLECTION_ORDERS[order_str]]
    return tuple(z_order)


def reorder_z_dim(data, order_packed, z_lengths, z_order, z_wanted):
    """Reorder the Z dimension of a numpy array.

    To fix the order of the Z dimension, we reshape the numpy array
    into the real 7 dimensions array that it is, tranpose it as
    necessary, and then reshape it back into the fake 5 dimensions.

    Args:
        data - numpy.array
        order_packed - tuple of 1 character
        z_lengths - tuple of 3 elements with the length of each of the
            dimensions packed in z, same order as z_order
        z_order - a 3 element tuple of 1 character, the order of the z
            dimension.
        z_wanted - a 3 element tuple of 1 character, with the wanted
            order of the z dimension.
    """
    assert data.ndim == len(order_packed), \
        "DATA ndims different from lenght of ORDER_PACKED"
    assert sorted(z_order) == ['a', 'p', 'z'], \
        "Z_ORDER does not have only 'a, z, p'"
    assert sorted(z_order) == sorted(z_wanted), \
        "Z_ORDER not same elements as Z_WANTED"

    z_idx = order_packed.index("z")
    order_in = order_packed[0:z_idx] + z_order + order_packed[z_idx+1:]
    order_out = order_packed[0:z_idx] + z_wanted + order_packed[z_idx+1:]

    packed_shape = data.shape
    unpacked_shape = packed_shape[0:z_idx] + z_lengths + packed_shape[z_idx+1:]

    ## The new order for the array axes
    dim_map = dict(zip(order_in, range(len(order_in))))
    axes_order = [dim_map[i] for i in order_out]

    data = data.reshape(unpacked_shape)
    data = numpy.transpose(data, axes_order)
    data = data.reshape(packed_shape)
    return data


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
            angleHandler = None, phaseHandler = None, polarizerHandler = None,
            slmHandler = None,
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
        self.polarizerHandler = polarizerHandler
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

        if self.slmHandler is not None:
            # Add a first trigger of the SLM to get first new image.
            table.addAction(curTime, self.slmHandler, 0)
            # Wait a few ms for any necessary SLM triggers.
            curTime = decimal.Decimal('5e-3')

        for angle, phase, z in self.genSIPositions():
            delayBeforeImaging = 0
            # Figure out which positions changed. They need to be held flat
            # up until the move, then spend some amount of time moving,
            # then have some time to stabilize. Or, if we have an SLM, then we
            # need to trigger it and then wait for it to stabilize.
            # Ensure we truly are doing this after all exposure events are done.
            curTime = max(curTime,
                          table.getFirstAndLastActionTimes()[1] + decimal.Decimal('1e-6'))
            if angle != prevAngle and prevAngle is not None:
                if self.angleHandler is not None:
                    motionTime, stabilizationTime = self.angleHandler.getMovementTime(prevAngle, angle)
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
            # expose handles the SLM triggers. This may result in an additional
            # short delay before exposure, but is the best way to support SIM
            # in a series of exposures at different wavelengths, with the SIM
            # pattern optimised for each wavelength.
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
        if self.polarizerHandler is not None:
            # Return to idle voltage.
            table.addAction(curTime, self.polarizerHandler, (None, 0))
            finalWaitTime = finalWaitTime + decimal.Decimal(1e-6)

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
            if longestWavelength in ['Ambient', 'ambient']:
                # SoftWorx uses -50 to represent transmitted light.
                longestWavelength = -50
            # Bleaching compensation
            tExpNew = tExp * (1 + decimal.Decimal(self.handlerToBleachCompensation[light]) * angle)
            newPairs.append((light, tExpNew))
        # Pre-exposure delay due to polarizer and SLM settling times.
        delay = decimal.Decimal(0.)
        # Set polarizer position
        if self.polarizerHandler is not None:
            table.addAction(curTime, self.polarizerHandler, (longestWavelength, angle))
            delay = max(delay, self.polarizerHandler.callbacks['getMovementTime']())
        # SLM trigger
        if self.slmHandler is not None:
            ## Add SLM event ot set pattern for phase, angle and longestWavelength.
            table.addAction(curTime, self.slmHandler, (angle, phase, longestWavelength))
            delay = max(delay, self.slmHandler.callbacks['getMovementTime']())
        curTime += delay
        return experiment.Experiment.expose(self, curTime, cameras, newPairs, table)


    def reorder_img_file(self):
        """Reorder the Z dimension in the file.

        Priism and Softworx are only capable to handle five dimensions
        so angle and phase get mixed in the Z dimension.  In addition,
        their reconstruction programs are only capable to handle them
        in angle-z-phase order.
        """
        z_order = collection_order_tuple(self.collectionOrder)
        z_wanted = ('a', 'z', 'p')
        if z_order == z_wanted:
            # Already in order; don't do anything.
            return

        length_getters = {
            "a" : self.numAngles,
            "z" : self.numZSlices,
            "p" : self.numPhases,
        }
        z_lengths = tuple([length_getters[d] for d in z_order])

        doc = util.datadoc.DataDoc(self.savePath)
        order_in = tuple(doc.image.Mrc.axisOrderStr())

        ## Read the extended header again separately.  It our case,
        ## this is a struct made of int32 and float32, one per plane.
        ## Its order also needs to be corrected.  We just fake a dtype
        ## with the right number of bytes per plane for the extended
        ## header.  We fake the struct by using multiple u1 per
        ## element.
        ext_header_stride = 4 * (doc.imageHeader.NumIntegers
                                 + doc.imageHeader.NumFloats)
        ext_header_dtype = ",".join(['u1']*ext_header_stride)
        with open(self.savePath, "rb") as fh:
            fh.seek(1024) # skip base header
            ext_header = numpy.fromfile(fh, count=doc.getNPlanes(),
                                        dtype=ext_header_dtype)
        assert doc.imageHeader.next == ext_header.nbytes, \
            "next value from datadoc differs from computed length"
        assert order_in[-2:] == ('y', 'x'), \
            "ORDER_IN two last dimensions are not Y and X"
        ext_header = ext_header.reshape(doc.image.shape[:-2])

        nfake_z = numpy.prod(z_lengths)
        assert doc.size[2] == nfake_z, \
            "num Z of doc differs from expected Z length"

        ## Finally, reorder the things.
        img_data = reorder_z_dim(doc.image, order_in, z_lengths,
                                 z_order, z_wanted)
        ext_header = reorder_z_dim(ext_header, order_in[:-2], z_lengths,
                                   z_order, z_wanted)

        ## Build a new header from old doc data

        ## Save to a new file, reusing the original base header since
        ## we don't actually changed anything there.
        tmp_fh = tempfile.NamedTemporaryFile(delete=False)
        util.datadoc.writeMrcHeader(doc.imageHeader, tmp_fh)
        ## Make sure the data is actually ordered for writing,
        ## otherwise at this point the arrays might be making use of
        ## views.
        ext_header = numpy.ascontiguousarray(ext_header)
        img_data = numpy.ascontiguousarray(img_data)
        tmp_fh.write(ext_header)
        tmp_fh.write(img_data)
        tmp_fh.close()

        ## We are going to swap the files now, so destroy the old
        ## datadoc which memmaps the old file or we won't be able to
        ## overwrite.
        del doc
        del img_data

        ## Windows needs to have the file removed first.
        if os.name == "nt":
            os.remove(self.savePath)
        shutil.move(tmp_fh.name, self.savePath)
        return


    def cleanup(self, runThread = None, saveThread = None):
        experiment.Experiment.cleanup(self, runThread, saveThread)
        if self.savePath:
            self.reorder_img_file()
        return


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
        params['polarizerHandler'] = depot.getHandlerWithName('SI polarizer')
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
