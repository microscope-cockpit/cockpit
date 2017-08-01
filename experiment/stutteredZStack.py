import actionTable
import events
import util.userConfig
import zStack

import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = 'Stuttered Z-stack'


## This class handles experiments where we alter the rate at which we take
# stacks as a function of time. E.g. (each | represents a single volume):
# ||||   |   |   |   ||||   |   |   |   |||| ...
class StutteredZStackExperiment(zStack.ZStackExperiment):
    ## \param sampleRates A list of (interval, numReps) tuples indicating
    #         the amount of time in seconds between each rep, and the
    #         number of reps to perform at that rate. If we hit the end of
    #         the list before running out of reps, then we recommence from
    #         the beginning.
    def __init__(self, sampleRates, *args, **kwargs):
        zStack.ZStackExperiment.__init__(self, *args, **kwargs)
        self.sampleRates = sampleRates
        self.shouldAbort = False

        events.subscribe('user abort', self.onAbort)


    ## User aborted.
    def onAbort(self):
        self.shouldAbort = True

        
    ## Call Experiment.execute() repeatedly, while varying self.numReps and
    # self.repDuration so that we do the right sequence with the right 
    # timings. 
    def execute(self):
        # HACK: replace self.numReps since it's used in Experiment.execute(),
        # which we will be calling from within this function. We'll handle
        # reps more directly.
        trueReps = self.numReps
        numRepsPerformed = 0
        sequenceIndex = 0
        wasSuccessful = True
        while numRepsPerformed < trueReps:
            interval, numReps = self.sampleRates[sequenceIndex % len(self.sampleRates)]
            numReps = min(numReps, trueReps - numRepsPerformed)
            # Set these values so that Experiment.execute() can use them
            # safely.
            self.numReps = numReps
            self.repDuration = interval
            # Run a normal experiment.
            wasSuccessful = zStack.ZStackExperiment.execute(self)
            sequenceIndex += 1
            numRepsPerformed += numReps
            if self.shouldAbort:
                return False
        return wasSuccessful



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = StutteredZStackExperiment



class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent = parent)

        self.configKey = configKey
        ## List of (interval in seconds, number of reps) tuples
        # representing the rate at which we should image the
        # sample.
        self.sampleRates = []

        sizer = wx.FlexGridSizer(2, 6, 2, 2)
        sizer.Add((0, 0))
        sizer.Add((0, 0))
        sizer.Add(wx.StaticText(self, -1, 'Sampling sequence'))
        sizer.Add(wx.StaticText(self, -1, 'Interval (s)'))
        sizer.Add(wx.StaticText(self, -1, 'Reps'))
        sizer.Add((0, 0))
        # Commence second row.
        button = wx.Button(self, -1, 'Clear')
        button.Bind(wx.EVT_BUTTON, self.onClear)
        button.SetToolTip(wx.ToolTip("Remove all entries"))
        sizer.Add(button)

        button = wx.Button(self, -1, 'Delete last')
        button.Bind(wx.EVT_BUTTON, self.onDeleteLast)
        button.SetToolTip(wx.ToolTip("Remove the most recently-added entry"))
        sizer.Add(button)

        self.sequenceText = wx.TextCtrl(self, -1,
                size = (200, -1), style = wx.TE_READONLY)
        self.sequenceText.SetToolTip(wx.ToolTip("Displays the sequence of " +
                "sampling intervals and reps we will perform for this " +
                "experiment."))
        sizer.Add(self.sequenceText)

        self.interval = wx.TextCtrl(self, -1, size = (60, -1))
        self.interval.SetToolTip(wx.ToolTip("Amount of time, in seconds, that " +
                "passes between each rep for this portion of the experiment."))
        sizer.Add(self.interval)

        self.numReps = wx.TextCtrl(self, -1, size = (60, -1))
        self.numReps.SetToolTip(wx.ToolTip("Number of reps to perform at this " +
                "sampling interval."))
        sizer.Add(self.numReps)

        button = wx.Button(self, -1, 'Add')
        button.Bind(wx.EVT_BUTTON, self.onAdd)
        button.SetToolTip(wx.ToolTip("Add this (interval, reps) pair to the sequence."))
        sizer.Add(button)

        self.SetSizerAndFit(sizer)


    ## User clicked the "Clear" button; wipe out our current settings.
    def onClear(self, event = None):
        self.sampleRates = []
        self.setText()


    ## User clicked the "Delete last" button; remove the most recent setting.
    def onDeleteLast(self, event = None):
        self.sampleRates = self.sampleRates[:-1]
        self.setText()


    ## User clicked the "Add" button; add the new pair to our settings.
    def onAdd(self, event = None):
        interval = float(self.interval.GetValue())
        numReps = int(self.numReps.GetValue())
        self.sampleRates.append((interval, numReps))
        self.interval.SetValue('')
        self.numReps.SetValue('')
        self.setText()


    ## Update our text display of the settings.
    def setText(self):
        text = ', '.join(["(%.2f, %d)" % (i, n) for (i, n) in self.sampleRates])
        self.sequenceText.SetValue(text)


    def augmentParams(self, params, shouldSave = True):
        if shouldSave:
            self.saveSettings()
        params['sampleRates'] = self.getSampleRates()
        return params


    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'StutteredZStackSettings',
                default = [])


    def getSampleRates(self):
        return self.sampleRates


    def getSettingsDict(self):
        return self.augmentParams({}, shouldSave = False)


    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'StutteredZStackSettings', settings)


