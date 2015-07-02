import actionTable
import experiment
import zStack
import gui.guiUtils as guiUtils
import depot

import decimal
import math
import wx

EXPERIMENT_NAME = 'STORM'

# We override the only method in ZStackExperiment but this makes the inheritance more clear.

class STORM2D(zStack.ZStackExperiment):


    ## Create the ActionTable needed to run the experiment. We simply move to
    # each Z-slice in turn, take all the images required for STORM,
    # and move the the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        curTime = 0
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        if self.zHeight > 1e-6:
            # Non-2D experiment; tack on an extra image to hit the top of
            # the volume.
            numZSlices += 1
        for zIndex in xrange(numZSlices):
            # Move to the next position, then wait for the stage to
            # stabilize.
            targetAltitude = self.sliceHeight * zIndex
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, targetAltitude)
            table.addAction(curTime + motionTime, self.zPositioner,
                    targetAltitude)
            curTime += motionTime + stabilizationTime
            prevAltitude = targetAltitude

            # Image the sample.
            for cameras, lightTimePairs in self.exposureSettings:
                curTime = self.expose(curTime, cameras, lightTimePairs, table)
                # Advance the time very slightly so that all exposures
                # are strictly ordered.
                curTime += decimal.Decimal('1e-10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, targetAltitude)

        # Move back to the start so we're ready for the next rep.
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
        table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
                self.zPositioner, 0)

        return table


EXPERIMENT_CLASS = STORM2D

class ExperimentUI(wx.Panel):

    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)

        self.configKey = configKey
        ## List of STORM sequences to add to actiontable.
        # STORM sequence: (numReps, {LIGHT:(duration, camera)})
        self.Sequences = []
        self.regenInput()

    # Everything expects 4 cols.
    def regenInput(self):
        rows = 2+len(self.Sequences)
        self.GlobalSizer = wx.FlexGridSizer(rows, 4, 5, 5)

        self.addTitleRow(self.GlobalSizer)
        for row in self.Sequences:
            addExperimentRow(self.GlobalSizer, row)
        self.addInputRow(self.GlobalSizer)

        self.GlobalSizer.Layout()
        self.SetSizerAndFit(self.GlobalSizer)

    def addExperimentRow(self, sizer, row):
        for spec in row:
            sizer.Add(wx.StaticText(self, -1, str(spec)))
        self.DelSequence = wx.Button(self, -1, 'Delete Sequence')
        self.DelSequence.Bind(wx.EVT_LEFT_DOWN, lambda event: self.removeSequenceEvent())
        sizer.Add(self.DelSequence)

    def addTitleRow(self, sizer):
        sizer.Add(wx.StaticText(self, -1, 'Light'))
        sizer.Add(wx.StaticText(self, -1, 'Number of repetitions'))
        sizer.Add(wx.StaticText(self, -1, 'Camera to use'))
        sizer.Add(wx.StaticText(self, -1, 'Add row'))

    def addInputRow(self, sizer):
        self.lightChoice = wx.Choice(self, choices=[str(light) for light in
                                                    depot.getHandlersOfType(depot.LIGHT_TOGGLE)])
        sizer.Add(self.lightChoice)

        self.repetitionsBox = wx.TextCtrl(self)
        sizer.Add(self.repetitionsBox)

        self.cameraChoice = wx.Choice(self, choices=[str(light) for light in
                                                    depot.getHandlersOfType(depot.CAMERA)])
        sizer.Add(self.cameraChoice)

        self.AddSequence = wx.Button(self, -1, 'Add Sequence')
        self.AddSequence.Bind(wx.EVT_LEFT_DOWN, lambda event: self.addSequenceEvent())
        sizer.Add(self.AddSequence)


    def addSequenceEvent(self):
        # TODO: check and typeconvert data
        row = (self.lightChoice.GetSelection(),
               self.repetitionsBox.GetValue(),
               self.cameraChoice.GetSelection())
        self.Sequences.append(row)
        self.regenInput()

    def removeSequenceEvent(self):
        pass
