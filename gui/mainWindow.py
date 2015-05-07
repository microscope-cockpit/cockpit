## This module creates the primary window. This window houses widgets to 
# control the most important hardware elements.

import json
import wx

import depot
import dialogs.experiment.multiSiteExperiment
import dialogs.experiment.singleSiteExperiment
import events
import experiment.experiment
import fileViewerWindow
import interfaces.imager
import keyboard
import toggleButton
import util.user
import util.userConfig
import viewFileDropTarget

## Window singleton
window = None

## Max width of rows of UI widgets.
# This number is chosen to match the width of the Macro Stage view.
MAX_WIDTH = 850



class MainWindow(wx.Frame):
    ## Construct the Window. We're only responsible for setting up the 
    # user interface; we assume that the devices have already been initialized.
    def __init__(self):
        wx.Frame.__init__(self, parent = None, title = "Cockpit program")

        # Find out what devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        lightToggles = sorted(lightToggles, key = lambda l: l.wavelength)
        # Set of objects that are in the same group as any light toggle.
        lightAssociates = set()
        for toggle in lightToggles:
            lightAssociates.update(depot.getHandlersInGroup(toggle.groupName))

        ## Maps LightSource handlers to their associated panels of controls.
        self.lightToPanel = dict()

        # Construct the UI.
        # Sizer for all controls. We'll split them into bottom half (light
        # sources) and top half (everything else).
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        # Panel for holding the non-lightsource controls.
        topPanel = wx.Panel(self)
        topPanel.SetBackgroundColour((170, 170, 170))
        topSizer = wx.BoxSizer(wx.VERTICAL)

        # A row of buttons for various actions we know we can take.
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        abortButton = toggleButton.ToggleButton(textSize = 16,
                label = "\nABORT", size = (120, 80), parent = topPanel,
                inactiveColor = wx.RED)
        abortButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: events.publish('user abort'))
        buttonSizer.Add(abortButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Single-site\nExperiment", size = (120, 80), 
                parent = topPanel)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: dialogs.experiment.singleSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Multi-site\nExperiment", size = (120, 80),
                parent = topPanel)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: dialogs.experiment.multiSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        viewFileButton = toggleButton.ToggleButton(textSize = 12,
                label = "View last\nfile", size = (120, 80),
                parent = topPanel)
        viewFileButton.Bind(wx.EVT_LEFT_DOWN,
                self.onViewLastFile)
        buttonSizer.Add(viewFileButton)
        self.videoButton = toggleButton.ToggleButton(textSize = 12,
                label = "Video mode", size = (120, 80), parent = topPanel)
        self.videoButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: interfaces.imager.videoMode())
        buttonSizer.Add(self.videoButton)
        saveButton = toggleButton.ToggleButton(textSize = 12,
                label = "Save Exposure\nSettings",
                size = (120, 80), parent = topPanel)
        saveButton.Bind(wx.EVT_LEFT_DOWN, self.onSaveExposureSettings)        
        buttonSizer.Add(saveButton)
        loadButton = toggleButton.ToggleButton(textSize = 12,
                label = "Load Exposure\nSettings",
                size = (120, 80), parent = topPanel)
        loadButton.Bind(wx.EVT_LEFT_DOWN, self.onLoadExposureSettings)        
        buttonSizer.Add(loadButton)
        snapButton = toggleButton.ToggleButton(textSize = 12,
                label = "Snap",
                size = (120, 80), parent = topPanel)
        snapButton.Bind(wx.EVT_LEFT_DOWN,
                        lambda event: interfaces.imager.takeImage())
        buttonSizer.Add(snapButton)

        
        topSizer.Add(buttonSizer)

        # Make UIs for any other handlers / devices and insert them into
        # our window, if possible.
        lightPowerThings = depot.getHandlersOfType(depot.LIGHT_POWER)
        lightPowerThings.sort(key = lambda l: l.wavelength)
        ignoreThings = lightToggles + list(lightAssociates) + lightPowerThings
        otherThings = depot.getAllDevices()
        # Sort devices by their class names; all we care about is a consistent
        # order to the elements of the UI. lightPowerThings are dealt with
        # separately, otherwise they appear in a random order.
        otherThings.sort(key = lambda d: d.__class__.__name__)
        otherThings.extend(depot.getAllHandlers())
        for thing in ignoreThings: 
            if thing in otherThings:
                otherThings.remove(thing)
        # Now make the UI elements for otherThings.
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        for thing in otherThings:
            item = thing.makeUI(topPanel)
            if item is not None:
                # Add it to the main controls display.
                if item.GetMinSize()[0] + rowSizer.GetMinSize()[0] > MAX_WIDTH:
                    # Start a new row, because the old one would be too
                    # wide to accommodate the item.
                    topSizer.Add(rowSizer, 1, wx.EXPAND)
                    rowSizer = wx.BoxSizer(wx.HORIZONTAL)
                if rowSizer.GetChildren():
                    # Add a spacer.
                    rowSizer.Add((1, -1), 1, wx.EXPAND)
                rowSizer.Add(item)

        topSizer.Add(rowSizer, 1)

        topPanel.SetSizerAndFit(topSizer)
        mainSizer.Add(topPanel)

        ## Panel for holding light sources.
        self.bottomPanel = wx.Panel(self)
        self.bottomPanel.SetBackgroundColour((170, 170, 170))
        bottomSizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self.bottomPanel, -1, "Illumination controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        bottomSizer.Add(label)
        lightSizer = wx.BoxSizer(wx.HORIZONTAL)
        # If we have a lot (more than 7) of light sources, then we hide
        # light sources by default and provide a listbox to let people show
        # only the ones they need.
        ## wx.ListBox of all lights, assuming we're using this UI modus.
        self.lightList = None
        if len(lightToggles) > 7:
            haveDynamicLightDisplay = True
            self.lightList = wx.ListBox(self.bottomPanel, -1,
                    size = (-1, 200), style = wx.LB_MULTIPLE,
                    choices = [light.name for light in lightToggles])
            self.lightList.Bind(wx.EVT_LISTBOX, self.onLightSelect)
            lightSizer.Add(self.lightList)
        # Construct the lightsource widgets. One column per light source.
        # Associated handlers on top, then then enable/disable toggle for the
        # actual light source, then exposure time, then any widgets that the
        # device code feels like adding.
        for light in lightToggles:
            lightPanel = wx.Panel(self.bottomPanel)
            self.lightToPanel[light] = lightPanel
            columnSizer = wx.BoxSizer(wx.VERTICAL)
            haveOtherHandler = False
            for otherHandler in depot.getHandlersInGroup(light.groupName):
                if otherHandler is not light:
                    columnSizer.Add(otherHandler.makeUI(lightPanel))
                    haveOtherHandler = True
                    break
            if not haveOtherHandler:
                # Put a spacer in so this widget has the same vertical size.
                columnSizer.Add((-1, 1), 1, wx.EXPAND)
            lightUI = light.makeUI(lightPanel)
            lightWidth = lightUI.GetSize()[0]
                
            columnSizer.Add(lightUI)
            events.publish('create light controls', lightPanel,
                    columnSizer, light)
            lightPanel.SetSizerAndFit(columnSizer)
            if self.lightList is not None:
                # Hide the panel by default; it will be shown only when
                # selected in the listbox.
                lightPanel.Hide()
            # Hack: the ambient light source goes first in the list.
            if 'Ambient' in light.groupName:
                lightSizer.Insert(0, lightPanel, 1, wx.EXPAND | wx.VERTICAL)
            else:
                lightSizer.Add(lightPanel, 1, wx.EXPAND | wx.VERTICAL)
        bottomSizer.Add(lightSizer)

        self.bottomPanel.SetSizerAndFit(bottomSizer)
        mainSizer.Add(self.bottomPanel)

        # Ensure we use our full width if possible.
        size = mainSizer.GetMinSize()
        if size[0] < MAX_WIDTH:
            mainSizer.SetMinSize((MAX_WIDTH, size[1]))
        
        self.SetSizerAndFit(mainSizer)

        keyboard.setKeyboardHandlers(self)
        self.SetDropTarget(viewFileDropTarget.ViewFileDropTarget(self))
        self.Bind(wx.EVT_MOVE, self.onMove)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        events.subscribe('user login', self.onUserLogin)
        events.subscribe('video mode toggle', self.onVideoMode)


    ## Save the position of our window. For all other windows, this is handled
    # by util.user.logout, but by the time that function gets called, we've
    # already been destroyed.
    def onMove(self, event):
        util.userConfig.setValue('mainWindowPosition', tuple(self.GetPosition()))


    ## Do any necessary program-shutdown events here instead of in the App's
    # OnExit, since in that function all of the WX objects have been destroyed
    # already.
    def onClose(self, event):
        events.publish('program exit')
        event.Skip()


    ## User logged in; update our title.
    def onUserLogin(self, username):
        self.SetTitle("Cockpit program (currently logged in as %s)" % username)


    ## Video mode has been turned on/off; update our button background.
    def onVideoMode(self, isEnabled):
        self.videoButton.setActive(isEnabled)


    ## User clicked the "view last file" button; open the last experiment's
    # file in an image viewer. A bit tricky when there's multiple files 
    # generated due to the splitting logic. We just view the first one in
    # that case.
    def onViewLastFile(self, event = None):
        filenames = experiment.experiment.getLastFilenames()
        if filenames:
            window = fileViewerWindow.FileViewer(filenames[0], self)
            if len(filenames) > 1:
                print "Opening first of %d files. Others can be viewed by dragging them from the filesystem onto the main window of the Cockpit." % len(filenames)


    ## User wants to save the current exposure settings; get a file path
    # to save to, collect exposure information via an event, and save it.
    def onSaveExposureSettings(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = "Please select where to save the settings.",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        settings = dict()
        events.publish('save exposure settings', settings)
        handle = open(dialog.GetPath(), 'w')
        handle.write(json.dumps(settings))
        handle.close()

    
    ## User wants to load an old set of exposure settings; get a file path
    # to load from, and publish an event with the data.
    def onLoadExposureSettings(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = "Please select the settings file to load.",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            # User cancelled.
            return
        handle = open(dialog.GetPath(), 'r')
        settings = json.loads('\n'.join(handle.readlines()))
        handle.close()
        events.publish('load exposure settings', settings)

        # If we're using the listbox approach to show/hide light controls,
        # then make sure all enabled lights are shown and vice versa.
        if self.lightList is not None:
            for i, name in enumerate(self.lightList.GetItems()):
                handler = depot.getHandlerWithName(name)
                self.lightList.SetStringSelection(name, handler.getIsEnabled())
            self.onLightSelect()


    ## User selected/deselected a light source from self.lightList; determine
    # which light panels should be shown/hidden.
    def onLightSelect(self, event = None):
        selectionIndices = self.lightList.GetSelections()
        items = self.lightList.GetItems()
        for light, panel in self.lightToPanel.iteritems():
            panel.Show(items.index(light.name) in selectionIndices)
        # Fix display. We need to redisplay ourselves as well in case the
        # newly-displayed lights are extending off the edge of the window.
        self.bottomPanel.SetSizerAndFit(self.bottomPanel.GetSizer())
        self.SetSizerAndFit(self.GetSizer())



## Create the window.
def makeWindow():
    global window
    window = MainWindow()
    window.Show()
    return window
