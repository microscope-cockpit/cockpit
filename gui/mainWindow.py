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

        ## Indicates which stage mover is currently under control.
        self.curMoverIndex = 0

        # Construct the UI.
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        # A row of buttons for various actions we know we can take.
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        abortButton = toggleButton.ToggleButton(textSize = 16,
                label = "\nABORT", size = (120, 80), parent = self,
                inactiveColor = wx.RED)
        abortButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: events.publish('user abort'))
        buttonSizer.Add(abortButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Single-site\nExperiment", size = (120, 80), 
                parent = self)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: dialogs.experiment.singleSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        experimentButton = toggleButton.ToggleButton(textSize = 12, 
                label = "Multi-site\nExperiment", size = (120, 80),
                parent = self)
        experimentButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: dialogs.experiment.multiSiteExperiment.showDialog(self))
        buttonSizer.Add(experimentButton)
        viewFileButton = toggleButton.ToggleButton(textSize = 12,
                label = "View last\nfile", size = (120, 80),
                parent = self)
        viewFileButton.Bind(wx.EVT_LEFT_DOWN,
                self.onViewLastFile)
        buttonSizer.Add(viewFileButton)
        videoButton = toggleButton.ToggleButton(textSize = 12,
                label = "Video mode", size = (120, 80), parent = self)
        videoButton.Bind(wx.EVT_LEFT_DOWN,
                lambda event: interfaces.imager.videoMode())
        buttonSizer.Add(videoButton)
        saveButton = toggleButton.ToggleButton(textSize = 12,
                label = "Save Exposure\nSettings",
                size = (120, 80), parent = self)
        saveButton.Bind(wx.EVT_LEFT_DOWN, self.onSaveExposureSettings)        
        buttonSizer.Add(saveButton)
        loadButton = toggleButton.ToggleButton(textSize = 12,
                label = "Load Exposure\nSettings",
                size = (120, 80), parent = self)
        loadButton.Bind(wx.EVT_LEFT_DOWN, self.onLoadExposureSettings)        
        buttonSizer.Add(loadButton)
        
        mainSizer.Add(buttonSizer)

        # Make UIs for any other handlers / devices and insert them into
        # our window, if possible.
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        allThings = depot.getAllDevices()
        # Sort devices by their class names; all we care about is a consistent
        # order to the elements of the UI.
        allThings.sort(key = lambda d: d.__class__.__name__)
        allThings.extend(depot.getAllHandlers())
        for thing in allThings:
            if thing not in lightToggles and thing not in lightAssociates:
                item = thing.makeUI(self)
                if item is not None:
                    # Add it to the main controls display.
                    if item.GetMinSize()[0] + rowSizer.GetMinSize()[0] > MAX_WIDTH:
                        # Start a new row, because the old one would be too
                        # wide to accommodate the item.
                        mainSizer.Add(rowSizer, 1, wx.EXPAND)
                        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
                    if rowSizer.GetChildren():
                        # Add a spacer.
                        rowSizer.Add((1, -1), 1, wx.EXPAND)
                    rowSizer.Add(item)
        mainSizer.Add(rowSizer, 1, wx.EXPAND)

        label = wx.StaticText(self, -1, "Illumination controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        mainSizer.Add(label)
        # Construct the lightsource widgets. Associated handlers on top, then
        # then enable/disable toggle for the actual light source.
        lightSizer = wx.BoxSizer(wx.HORIZONTAL)
        for light in lightToggles:
            columnSizer = wx.BoxSizer(wx.VERTICAL)
            haveOtherHandler = False
            for otherHandler in depot.getHandlersInGroup(light.groupName):
                if otherHandler is not light:
                    columnSizer.Add(otherHandler.makeUI(self))
                    haveOtherHandler = True
                    break
            if not haveOtherHandler:
                # Put a spacer in so this widget has the same vertical size.
                columnSizer.Add((-1, 1), 1, wx.EXPAND)
            columnSizer.Add(light.makeUI(self))
            events.publish('create light controls', self, columnSizer, light)
            # Hack: the ambient light source goes first in the list.
            if 'Ambient' in light.groupName:
                lightSizer.Insert(0, columnSizer, 1, wx.EXPAND | wx.VERTICAL)
            else:
                lightSizer.Add(columnSizer, 1, wx.EXPAND | wx.VERTICAL)
        mainSizer.Add(lightSizer)

        # Ensure we use our full width if possible.
        size = mainSizer.GetMinSize()
        if size[0] < MAX_WIDTH:
            mainSizer.SetMinSize((MAX_WIDTH, size[1]))
        
        self.SetSizerAndFit(mainSizer)

        keyboard.setKeyboardHandlers(self)
        self.SetDropTarget(DropTarget(self))
        self.Bind(wx.EVT_MOVE, self.onMove)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        events.subscribe('user login', self.onUserLogin)


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


    ## User clicked the "view last file" button; open the last experiment's
    # file in an image viewer.
    def onViewLastFile(self, event = None):
        filename = experiment.experiment.getLastFilename()
        if filename is not None:
            window = fileViewerWindow.FileViewer(filename, self)


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

            

## Allow users to drag files onto this window to pop up a viewer.
class DropTarget(wx.FileDropTarget):
    def __init__(self, parent):
        wx.FileDropTarget.__init__(self)
        self.parent = parent

        
    def OnDropFiles(self, x, y, filenames):
        for filename in filenames:
            window = fileViewerWindow.FileViewer(filename, self.parent)
        


## Create the window.
def makeWindow():
    global window
    window = MainWindow()
    window.Show()
    return window
