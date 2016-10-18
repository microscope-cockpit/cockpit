import wx

import events
import gui.toggleButton
import util.threads

## This module creates the "status lights" window which tells the user
# various information about their environment.


class StatusLightsWindow(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title = "Status information",
                style = wx.RESIZE_BORDER | wx.CAPTION | wx.FRAME_TOOL_WINDOW)
        self.panel = wx.Panel(self)

        ## Maps status light names to the lights themselves. Each light is
        # a ToggleButton instance.
        self.nameToLight = {}

        events.subscribe('new status light', self.onNewLight)
        events.subscribe('update status light', self.onNewStatus)

        # Some lights that we know we need.
        self.onNewLight('image count', '')
        self.onNewLight('device waiting', '')
        self.Show()


    ## New light generated; insert it into our panel.
    # Do nothing if the light already exists.
    @util.threads.callInMainThread
    def onNewLight(self, lightName, text, backgroundColor = None):
        if lightName in self.nameToLight:
            return
        if backgroundColor is None:
            backgroundColor = (170, 170, 170)
        light = gui.toggleButton.ToggleButton(parent = self.panel,
                activeColor = backgroundColor, activeLabel = text,
                size = (170, 100))
        # For some reason, using a sizer here causes the lights to be placed
        # on top of each other...so I'm just setting sizes manually. HACK.
        self.nameToLight[lightName] = light
        light.SetPosition((170 * (len(self.nameToLight) - 1), 0))
        self.panel.SetClientSize((170 * len(self.nameToLight), 100))
        self.SetClientSize(self.panel.GetSize())


    ## Update the status light with the specified name. Create the light
    # if it doesn't already exist.
    @util.threads.callInMainThread
    def onNewStatus(self, lightName, text, backgroundColor = None):
        if lightName not in self.nameToLight:
            self.onNewLight(lightName, text, backgroundColor)
        else:
            self.nameToLight[lightName].SetLabel(text)
            if backgroundColor is not None:
                self.nameToLight[lightName].SetBackgroundColour(backgroundColor)
            self.nameToLight[lightName].Refresh()



## Global singleton.
window = None

def makeWindow(parent):
    global window
    window = StatusLightsWindow(parent)
    
