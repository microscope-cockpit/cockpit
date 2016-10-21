import wx

import depot
import deviceHandler

import events
import gui.guiUtils
import gui.keyboard
import gui.toggleButton


## This handler is responsible for tracking the current objective. 
class ObjectiveHandler(deviceHandler.DeviceHandler):
    ## \param nameToPixelSize A mapping of objective names to how many microns
    #         wide a pixel using that objective appears to be.
    # \param curObjective Currently-active objective.
    # \param callbacks
    # - setObjective(name, objectiveName): Set the current objective to the
    #   named one. This is an optional callback; if not provided, nothing is
    #   done.
    def __init__(self, name, groupName, nameToPixelSize, nameToTransform, nameToOffset, nameToColour, nameToLensID, curObjective,
            callbacks = {}):
        deviceHandler.DeviceHandler.__init__(self, name, groupName, 
                False, {}, depot.OBJECTIVE)
        self.nameToPixelSize = nameToPixelSize
        self.nameToTransform = nameToTransform
        self.nameToOffset = nameToOffset
        self.nameToColour = nameToColour
        self.nameToLensID = nameToLensID
        self.curObjective = curObjective
        self.callbacks = callbacks
        ## List of ToggleButtons, one per objective.
        self.buttons = []

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.curObjective


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            self.changeObjective(settings[self.name])


    ## Generate a row of buttons, one for each possible objective.
    def makeUI(self, parent):
        frame = wx.Frame(parent, title = "Objectives",
                style = wx.RESIZE_BORDER | wx.CAPTION | wx.FRAME_TOOL_WINDOW)
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        for name in sorted(self.nameToPixelSize.keys()):
            colour = self.nameToColour.get(name)
            colour= (colour[0]*255,colour[1]*255,colour[2]*255)
            button = gui.toggleButton.ToggleButton(
                activeColor = colour,
                label = name, parent = panel, 
                size = (80, 40))
            button.Bind(wx.EVT_LEFT_DOWN, 
                    lambda event, name = name: self.changeObjective(name))
            sizer.Add(button)
            self.buttons.append(button)
        panel.SetSizerAndFit(sizer)
        frame.SetClientSize(panel.GetSize())
        frame.SetPosition((2160, 0))
        frame.Show()
        gui.keyboard.setKeyboardHandlers(frame)
        return None


    ## Let everyone know what the initial objective.
    def makeInitialPublications(self):
        self.changeObjective(self.curObjective)


    ## Let everyone know that the objective has been changed.
    def changeObjective(self, newName):
        if 'setObjective' in self.callbacks:
            self.callbacks['setObjective'](self.name, newName)
        self.curObjective = newName
        events.publish("objective change", newName, 
                pixelSize=self.nameToPixelSize[newName], 
                transform=self.nameToTransform[newName],
                offset=self.nameToOffset[newName])				
        targetIndex = sorted(self.nameToPixelSize.keys()).index(newName)
        for i, button in enumerate(self.buttons):
            button.setActive(i == targetIndex)
                

    ## Get the current pixel size.
    def getPixelSize(self):
        return self.nameToPixelSize[self.curObjective]
		
    ## Get the current offset.
    def getOffset(self):
        return self.nameToOffset[self.curObjective]

    ## Get Current lensID for file metadata.
    def getLensID(self):
        return self.nameToLensID[self.curObjective]
