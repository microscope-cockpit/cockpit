import depot
import experiment.experimentRegistry
import gui.guiUtils
import gui.saveTopBottomPanel
import interfaces.stageMover
import util.logger
import util.userConfig
import util.user

import collections
import datetime
import decimal
import numpy
import json
import os
import time
import traceback
import wx

## @package dialogs.experimentConfigPanel
# This module holds the ExperimentConfigPanel class and associated constants.

## List of Z positioning modes.
Z_POSITION_MODES = ['Current is center', 'Current is bottom',
        'Use saved top/bottom']



## This class provides a GUI for setting up and running experiments, in the
# form of an embeddable wx.Panel and a selection of functions. To use the
# panel, create an instance of ExperimentConfigPanel and insert it into your
# GUI. Call its runExperiment function when you are ready to start the
# experiment.
#
# The parent is required to implement onExperimentPanelResize so that changes
# in the panel size will be handled properly.
class ExperimentConfigPanel(wx.Panel):
    ## Instantiate the class. Pull default values out of the config file, and
    # create the UI and layout.
    # \param resizeCallback Function to call when we have changed size.
    # \param resetCallback Function to call to force a reset of the panel.
    # \param configKey String used to look up settings in the user config. This
    #        allows different experiment panels to have different defaults.
    # \param shouldShowFileControls True if we want to show the file suffix
    #        and filename controls, False otherwise (typically because we're
    #        encapsulated by some other system that handles its own filenames).
    def __init__(self, parent, resizeCallback, resetCallback,
            configKey = 'singleSiteExperiment', shouldShowFileControls = True):
        wx.Panel.__init__(self, parent, style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL)
        self.parent = parent

        self.configKey = configKey
        self.resizeCallback = resizeCallback
        self.resetCallback = resetCallback

        ## experiment.Experiment subclass instance -- mostly preserved for
        # debugging, so we can examine the state of the experiment.
        self.runner = None

        self.allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        self.allLights.sort(key = lambda l: l.wavelength)
        self.allCameras = depot.getHandlersOfType(depot.CAMERA)
        self.allCameras.sort(key = lambda c: c.name)

        ## Map of default settings as loaded from config.
        self.settings = self.loadConfig()

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # Section for settings that are universal to all experiment types.
        universalSizer = wx.FlexGridSizer(2, 3, 5, 5)

        ## Maps experiment description strings to experiment modules.
        self.experimentStringToModule = collections.OrderedDict()
        for module in experiment.experimentRegistry.getExperimentModules():
            self.experimentStringToModule[module.EXPERIMENT_NAME] = module            
        
        self.experimentType = wx.Choice(self,
                choices = self.experimentStringToModule.keys())
        self.experimentType.SetSelection(0)
        gui.guiUtils.addLabeledInput(self, universalSizer,
                label = "Experiment type:", control = self.experimentType)

        self.numReps = gui.guiUtils.addLabeledInput(self,
                universalSizer, label = "Number of reps:",
                defaultValue = self.settings['numReps'])

        self.repDuration = gui.guiUtils.addLabeledInput(self,
                universalSizer, label = "Rep duration (s):",
                defaultValue = self.settings['repDuration'],
                helperString = "Amount of time that must pass between the start " +
                "of each rep. Use 0 if you don't want any wait time.")

        self.zPositionMode = wx.Choice(self, choices = Z_POSITION_MODES)
        self.zPositionMode.SetSelection(0)
        gui.guiUtils.addLabeledInput(self, universalSizer,
                label = "Z position mode:", control = self.zPositionMode)

        self.stackHeight = gui.guiUtils.addLabeledInput(self,
                universalSizer, label = u"Stack height (\u03bcm):",
                defaultValue = self.settings['stackHeight'])

        self.sliceHeight = gui.guiUtils.addLabeledInput(self,
                universalSizer, label = u"Slice height (\u03bcm):",
                defaultValue = self.settings['sliceHeight'])

        self.sizer.Add(universalSizer, 0, wx.ALL, 5)

        ## Maps experiment modules to ExperimentUI instances holding the
        # UI for that experiment, if any.
        self.experimentModuleToPanel = {}
        for module in self.experimentStringToModule.values():
            if not hasattr(module, 'ExperimentUI'):
                # This experiment type has no special UI to set up.
                continue
            panel = module.ExperimentUI(self, self.configKey)
            panel.Hide()
            self.sizer.Add(panel)
            self.experimentModuleToPanel[module] = panel
        self.experimentType.Bind(wx.EVT_CHOICE, self.onExperimentTypeChoice)
        self.onExperimentTypeChoice()

        # Section for exposure settings. We allow either setting per-laser
        # exposure times and activating all cameras as a group, or setting
        # them per-laser and per-camera (and activating each camera-laser
        # grouping in sequence).
        exposureSizer = wx.BoxSizer(wx.VERTICAL)

        ## Controls which set of exposure settings we enable.
        self.shouldExposeSimultaneously = wx.CheckBox(
                self, label = "Expose all cameras simultaneously")
        exposureSizer.Add(self.shouldExposeSimultaneously, 0, wx.ALL, 5)
        ## Panel for holding controls for when we expose every camera
        # simultaneously.
        self.simultaneousExposurePanel = wx.Panel(self)
        simultaneousSizer = wx.BoxSizer(wx.VERTICAL)
        simultaneousSizer.Add(
                wx.StaticText(self.simultaneousExposurePanel, -1, "Exposure times for light sources:"),
                0, wx.ALL, 5)
        
        ## Ordered list of exposure times for simultaneous exposure mode.
        self.lightExposureTimes, timeSizer = gui.guiUtils.makeLightsControls(
                self.simultaneousExposurePanel,
                [str(l.name) for l in self.allLights],
                self.settings['simultaneousExposureTimes'])
        simultaneousSizer.Add(timeSizer)
        useCurrentButton = wx.Button(self.simultaneousExposurePanel, -1, 
                "Use current settings")
        useCurrentButton.SetToolTip(wx.ToolTip("Use the same settings as are currently used to take images with the '+' button"))
        useCurrentButton.Bind(wx.EVT_BUTTON, self.onUseCurrentExposureSettings)
        simultaneousSizer.Add(useCurrentButton)

        self.simultaneousExposurePanel.SetSizerAndFit(simultaneousSizer)
        exposureSizer.Add(self.simultaneousExposurePanel, 0, wx.ALL, 5)

        ## Panel for when we expose each camera in sequence.        
        self.sequencedExposurePanel = wx.Panel(self)
        ## Maps a camera handler to an ordered list of exposure times. 
        self.cameraToExposureTimes = {}
        sequenceSizer = wx.FlexGridSizer(
                len(self.settings['sequencedExposureSettings']) + 1,
                len(self.settings['sequencedExposureSettings'][0]) + 1,
                1)
        for label in [''] + [str(l.name) for l in self.allLights]:
            sequenceSizer.Add(
                    wx.StaticText(self.sequencedExposurePanel, -1, label),
                    0, wx.ALIGN_RIGHT | wx.ALL, 5)
        for i, camera in enumerate(self.allCameras):
            sequenceSizer.Add(
                    wx.StaticText(self.sequencedExposurePanel, -1, str(camera.name)),
                    0, wx.TOP | wx.ALIGN_RIGHT, 8)
            times = []
            for defaultVal in self.settings['sequencedExposureSettings'][i]:
                exposureTime = wx.TextCtrl(
                        self.sequencedExposurePanel, size = (40, -1))
                exposureTime.SetValue(defaultVal)
                sequenceSizer.Add(exposureTime, 0, wx.ALL, 5)
                times.append(exposureTime)
            self.cameraToExposureTimes[camera] = times
        self.sequencedExposurePanel.SetSizerAndFit(sequenceSizer)        
        exposureSizer.Add(self.sequencedExposurePanel, 0, wx.ALL, 5)
        self.sizer.Add(exposureSizer)

        # Toggle which panel is displayed based on the checkbox.
        self.shouldExposeSimultaneously.Bind(wx.EVT_CHECKBOX, self.onExposureCheckbox)
        self.shouldExposeSimultaneously.SetValue(self.settings['shouldExposeSimultaneously'])
        self.onExposureCheckbox()

        # File controls.
        self.filePanel = wx.Panel(self)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.filenameSuffix = gui.guiUtils.addLabeledInput(self.filePanel,
                rowSizer, label = "Filename suffix:",
                defaultValue = self.settings['filenameSuffix'],
                size = (160, -1))
        self.filenameSuffix.Bind(wx.EVT_KEY_DOWN, self.generateFilename)
        self.filename = gui.guiUtils.addLabeledInput(self.filePanel,
                rowSizer, label = "Filename:", size = (200, -1))
        self.generateFilename()
        updateButton = wx.Button(self.filePanel, -1, 'Update')
        updateButton.SetToolTip(wx.ToolTip(
                "Generate a new filename based on the current time " +
                "and file suffix."))
        updateButton.Bind(wx.EVT_BUTTON, self.generateFilename)
        rowSizer.Add(updateButton)
        self.filePanel.SetSizerAndFit(rowSizer)
        self.filePanel.Show(shouldShowFileControls)
        self.sizer.Add(self.filePanel, 0, wx.LEFT, 5)

        # Save/load experiment settings buttons.
        saveLoadPanel = wx.Panel(self)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        saveButton = wx.Button(saveLoadPanel, -1, "Save experiment settings...")
        saveButton.Bind(wx.EVT_BUTTON, self.onSaveExperiment)
        rowSizer.Add(saveButton, 0, wx.ALL, 5)
        loadButton = wx.Button(saveLoadPanel, -1, "Load experiment settings...")
        loadButton.Bind(wx.EVT_BUTTON, self.onLoadExperiment)
        rowSizer.Add(loadButton, 0, wx.ALL, 5)
        saveLoadPanel.SetSizerAndFit(rowSizer)
        self.sizer.Add(saveLoadPanel, 0, wx.LEFT, 5)
        
        self.SetSizerAndFit(self.sizer)


    ## Load values from config, and validate them -- since devices may get
    # changed out from under us, rendering some config entries (e.g. dealing
    # with light sources) invalid.
    def loadConfig(self):
        result = util.userConfig.getValue(self.configKey, default = {
                'filenameSuffix': '',
                'numReps': '1',
                'repDuration': '0',
                'sequencedExposureSettings': [['' for l in self.allLights] for c in self.allCameras],
                'shouldExposeSimultaneously': True,
                'simultaneousExposureTimes': ['' for l in self.allLights],
                'sliceHeight': '.15',
                'stackHeight': '4',
                'ZPositionMode': 0,
            }
        )
        for key in ['simultaneousExposureTimes']:
            if len(result[key]) != len(self.allLights):
                # Number of light sources has changed; invalidate the config.
                result[key] = ['' for light in self.allLights]
        key = 'sequencedExposureSettings'
        if (len(result[key]) != len(self.allCameras) or 
                len(result[key][0]) != len(self.allLights)):
            # Number of lights and/or number of cameras has changed.
            result[key] = [['' for l in self.allLights] for c in self.allCameras]
        return result


    ## User selected a different experiment type; show/hide specific
    # experiment parameters as appropriate; depending on experiment type, 
    # some controls may be enabled/disabled.
    def onExperimentTypeChoice(self, event = None):
        newType = self.experimentType.GetStringSelection()
        for expString, module in self.experimentStringToModule.iteritems():
            if module in self.experimentModuleToPanel:
                # This experiment module has a special UI panel which needs
                # to be shown/hidden.
                panel = self.experimentModuleToPanel[module]
                panel.Show(expString == newType)
        self.SetSizerAndFit(self.sizer)
        self.resizeCallback(self)


    ## User toggled the exposure controls; show/hide the panels as
    # appropriate.
    def onExposureCheckbox(self, event = None):
        val = self.shouldExposeSimultaneously.GetValue()
        self.simultaneousExposurePanel.Show(val)
        self.sequencedExposurePanel.Show(not val)
        self.SetSizerAndFit(self.sizer)
        self.resizeCallback(self)


    ## User clicked the "Use current settings" button; fill out the 
    # simultaneous-exposure settings text boxes with the current
    # interactive-mode exposure settings.
    def onUseCurrentExposureSettings(self, event = None):
        for i, light in enumerate(self.allLights):
            # Only have an exposure time if the light is enabled.
            val = ''
            if light.getIsEnabled():
                val = str(light.getExposureTime())
            self.lightExposureTimes[i].SetValue(val)


    ## User clicked the "Save experiment settings..." button; save the
    # parameters for later use as a JSON dict.
    def onSaveExperiment(self, event = None):
        settings = self.getSettingsDict()
        # Augment the settings with information pertinent to our current
        # experiment.
        experimentType = self.experimentType.GetStringSelection()
        settings['experimentType'] = experimentType
        module = self.experimentStringToModule[experimentType]
        if module in self.experimentModuleToPanel:
            # Have specific parameters for this experiment type; store them
            # too.
            settings['experimentSpecificValues'] = self.experimentModuleToPanel[module].getSettingsDict()

        # Get the filepath to save settings to.
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = 'Please select where to save the experiment.',
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        filepath = dialog.GetPath()
        handle = open(filepath, 'w')
        try:
            handle.write(json.dumps(settings))
        except Exception, e:
            util.logger.log.error("Couldn't save experiment settings: %s" % e)
            util.logger.log.error(traceback.format_exc())
            util.logger.log.error("Settings are:\n%s" % str(settings))
        handle.close()
        

    ## User clicked the "Load experiment settings..." button; load the
    # parameters from a file.
    def onLoadExperiment(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = 'Please select the experiment file to load.',
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        filepath = dialog.GetPath()
        handle = open(filepath, 'r')
        settings = json.loads(' '.join(handle.readlines()))
        handle.close()
        experimentType = settings['experimentType']
        experimentIndex = self.experimentType.FindString(experimentType)
        module = self.experimentStringToModule[experimentType]
        if module in self.experimentModuleToPanel:
            panel = self.experimentModuleToPanel[module]
            panel.saveSettings(settings['experimentSpecificValues'])
            del settings['experimentSpecificValues']
        util.userConfig.setValue(self.configKey, settings)
        # Reset the panel, destroying us and creating a new panel with
        # the proper values in all parameters, except for experiment type.
        panel = self.resetCallback()
        panel.experimentType.SetSelection(experimentIndex)
        panel.onExperimentTypeChoice()


    ## Generate a filename, based on the current time and the
    # user's chosen file suffix.
    def generateFilename(self, event = None):
        # HACK: if the event came from the user typing into the suffix box,
        # then we need to let it go through so that the box gets updated,
        # and we have to wait to generate the new filename until after that
        # point (otherwise we get the old value before) the user hit any keys).
        if event is not None:
            event.Skip()
            wx.CallAfter(self.generateFilename)
        else:
            suffix = self.filenameSuffix.GetValue()
            if suffix:
                suffix = '_' + suffix
            base = time.strftime('%Y%m%d-%H%M%S', time.localtime())
            self.filename.SetValue("%s%s" % (base, suffix))


    ## Set the filename.
    def setFilename(self, newName):
        self.filename.SetValue(newName)
    

    ## Run the experiment per the user's settings.
    def runExperiment(self):
        self.saveSettings()
        # Find the Z mover with the smallest range of motion, assumed
        # to be our experiment mover.
        mover = depot.getSortedStageMovers()[2][-1]
        # Only use active cameras and enabled lights.
        cameras = filter(lambda c: c.getIsEnabled(), 
                depot.getHandlersOfType(depot.CAMERA))
        if not cameras:
            wx.MessageDialog(self,
                    message = "No cameras are enabled, so the experiment cannot be run.",
                    style = wx.ICON_EXCLAMATION | wx.STAY_ON_TOP | wx.OK).ShowModal()
            return
        lights = filter(lambda l: l.getIsEnabled(), 
                depot.getHandlersOfType(depot.LIGHT_TOGGLE))
        
        exposureSettings = []
        if self.shouldExposeSimultaneously.GetValue():
            # A single exposure event with all cameras and lights.
            lightTimePairs = []
            for i, light in enumerate(self.allLights):
                if (self.allLights[i].getIsEnabled() and
                        self.lightExposureTimes[i].GetValue()):
                    lightTimePairs.append(
                        (light, gui.guiUtils.tryParseNum(self.lightExposureTimes[i], decimal.Decimal)))
            exposureSettings = [(cameras, lightTimePairs)]
        else:
            # A separate exposure for each camera.
            for camera in cameras:
                cameraSettings = self.cameraToExposureTimes[camera]
                settings = []
                for i, light in enumerate(self.allLights):
                    if not light.getIsEnabled():
                        continue
                    timeControl = cameraSettings[i]
                    if timeControl.GetValue():
                        settings.append((light, gui.guiUtils.tryParseNum(timeControl, decimal.Decimal)))
                exposureSettings.append(([camera], settings))
                
        curZ = interfaces.stageMover.getPositionForAxis(2)
        # Default to "current is bottom"
        zBottom = curZ
        zHeight = gui.guiUtils.tryParseNum(self.stackHeight, float)
        if self.zPositionMode.GetStringSelection() == 'Current is center':
            zBottom = curZ - zHeight / 2
        elif self.zPositionMode.GetStringSelection() == 'Use saved top/bottom':
            zBottom, zTop = gui.saveTopBottomPanel.getBottomAndTop()
            zHeight = zTop - zBottom

        sliceHeight = gui.guiUtils.tryParseNum(self.sliceHeight, float)
        if zHeight == 0:
            # 2D mode.
            zHeight = 1e-6
            sliceHeight = 1e-6

        savePath = os.path.join(util.user.getUserSaveDir(),
                self.filename.GetValue())
        params = {
                'numReps': gui.guiUtils.tryParseNum(self.numReps),
                'repDuration': gui.guiUtils.tryParseNum(self.repDuration, float),
                'zPositioner': mover,
                'zBottom': zBottom,
                'zHeight': zHeight,
                'sliceHeight': sliceHeight,
                'cameras': cameras,
                'lights': lights,
                'exposureSettings': exposureSettings,
                'savePath': savePath
        }
        experimentType = self.experimentType.GetStringSelection()
        module = self.experimentStringToModule[experimentType]
        if module in self.experimentModuleToPanel:
            # Add on the special parameters needed by this experiment type.
            params = self.experimentModuleToPanel[module].augmentParams(params)

        self.runner = module.EXPERIMENT_CLASS(**params)
        self.runner.run()


    ## Generate a dict of our current settings.
    def getSettingsDict(self):
        sequencedExposureSettings = []
        for i, camera in enumerate(self.allCameras):
            sequencedExposureSettings.append([c.GetValue() for c in self.cameraToExposureTimes[camera]])
        simultaneousTimes = [c.GetValue() for c in self.lightExposureTimes]
        
        newSettings = {
                'filenameSuffix': self.filenameSuffix.GetValue(),
                'numReps': self.numReps.GetValue(),
                'repDuration': self.repDuration.GetValue(),
                'sequencedExposureSettings': sequencedExposureSettings,
                'shouldExposeSimultaneously': self.shouldExposeSimultaneously.GetValue(),
                'simultaneousExposureTimes': simultaneousTimes,
                'sliceHeight': self.sliceHeight.GetValue(),
                'stackHeight': self.stackHeight.GetValue(),
                'ZPositionMode': self.zPositionMode.GetSelection(),
        }
        return newSettings


    ## Save the current experiment settings to config.
    def saveSettings(self):
        util.userConfig.setValue(self.configKey, self.getSettingsDict())
    
