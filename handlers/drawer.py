import wx

import depot
import deviceHandler

import events
import gui.guiUtils
import gui.keyboard
import gui.toggleButton

from util.colors import dyeToColor

## This handler is responsible for tracking what kinds of light each camera
# receives, via the drawer system.
class DrawerHandler(deviceHandler.DeviceHandler):
    ## We allow either for a set of pre-chosen filters (via DrawerSettings),
    # or for a more variable approach with callbacks. If callbacks are
    # supplied, they override the DrawerSettings if any. 
    # \param settings A list of DrawerSettings instances.
    # \param settingIndex Index into settings list indicating the current mode.
    def __init__(self, name, groupName, settings = None, settingIndex = None,
                 callbacks = {}):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.DRAWER)
        self.settings = settings
        self.settingIndex = settingIndex
        ## List of ToggleButtons, one per setting.
        self.buttons = []
        # Last thing to do is update UI to show default selections.
        events.subscribe('cockpit initialization complete', self.changeDrawer)


    ## Generate a row of buttons, one for each possible drawer.
    def makeUI(self, parent):
        if not self.settings or len(self.settings) == 1:
            # Nothing to be done here.
            return None
        frame = wx.Frame(parent, title = "Drawers",
                style = wx.RESIZE_BORDER | wx.CAPTION | wx.FRAME_TOOL_WINDOW)
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        for setting in self.settings:
            button = gui.toggleButton.ToggleButton(
                    label = setting.name, parent = panel, 
                    size = (80, 40))
            button.Bind(wx.EVT_LEFT_DOWN, 
                    lambda event, setting = setting: self.changeDrawer(setting))
            sizer.Add(button)
            self.buttons.append(button)
        panel.SetSizerAndFit(sizer)
        frame.SetClientSize(panel.GetSize())
        frame.SetPosition((2400, 65))
        frame.Show()
        gui.keyboard.setKeyboardHandlers(frame)
        return None


    ## Set dye and wavelength on each camera, and update our UI.
    def changeDrawer(self, newSetting=None):
        if newSetting is None:
            ns = self.settings[0]
        else:
            ns = newSetting
            self.settingIndex = self.settings.index(ns)
        for cname in ns.cameraNames:
            h = depot.getHandler(cname, depot.CAMERA)
            h.updateFilter(ns.cameraToDye[cname], ns.cameraToWavelength[cname])
        for i, b in enumerate(self.buttons):
            state = i == self.settingIndex
            b.updateState(state)


## This is a simple container class to describe a single drawer. 
class DrawerSettings:
    ## All parameters except the drawer name are lists, and the lists refer to
    # cameras in the same orders.
    # \param name Name used to refer to the drawer. 
    # \param cameraNames Unique names for each camera. These are the same 
    #        across all drawers.
    # \param dyeNames Names of dyes that roughly correspond to the wavelengths
    #        that the cameras see.
    # \param wavelengths Numerical wavelengths corresponding to the bandpass
    #        filters in front of the cameras.
    def __init__(self, name, cameraNames, dyeNames, wavelengths):
        self.name = name
        self.cameraNames = cameraNames
        self.dyeNames = dyeNames
        self.wavelengths = wavelengths
        self.cameraToDye = dict(zip(cameraNames, dyeNames))
        self.cameraToWavelength = dict(zip(cameraNames, wavelengths))

    def update(self, cameraName, dyeName, wavelength):
        for i, camera in enumerate(self.cameraNames):
            if camera == cameraName:
                self.dyeNames[i] = dyeName
                self.wavelengths[i] = wavelength
                break
        else:
            # Didn't find the camera name.
            self.cameraNames.append(cameraName)
            self.dyeNames.append(dyeName)
            self.wavelengths.append(wavelength)
        self.cameraToDye = dict(zip(self.cameraNames, self.dyeNames))
        self.cameraToWavelength = dict(zip(self.cameraNames, self.wavelengths))