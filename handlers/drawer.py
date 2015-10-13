import wx

import depot
import deviceHandler

import events
import gui.guiUtils
import gui.keyboard
import gui.toggleButton

from util.colors import wavelengthToColor


## Maps dye names to colors to use for those dyes.
DYE_TO_COLOR = {
        'Cy5': (0, 255, 255),
        'DAPI': (184, 0, 184),
        'DIC': (128, 128, 128),
        'FITC': (80,255,150),
        'GFP': (0, 255, 0),
        'mCherry': (255, 0, 0),
        'RFP': (255, 0, 0),
        'Rhod': (255,80,20),
        'YFP': (255, 255, 0),
        'TRITC': (255,165,0),
        'ND': (200, 200, 200)
}



## This handler is responsible for tracking what kinds of light each camera
# receives, via the drawer system.
class DrawerHandler(deviceHandler.DeviceHandler):
    ## We allow either for a set of pre-chosen filters (via DrawerSettings),
    # or for a more variable approach with callbacks. If callbacks are
    # supplied, they override the DrawerSettings if any. 
    # \param settings A list of DrawerSettings instances.
    # \param settingIndex Index into settings list indicating the current mode.
    # \param callbacks If available, must implement:
    # - getWavelengthForCamera(name, cameraName): return the wavelength of
    #   light seen by that camera.
    # - getDyeForCamera(name, cameraName): return the name of the dye the
    #   camera sees, or some other textual description (e.g. "Full")
    # - getColorForCamera(name, cameraName): return the color used to
    #   represent the named camera.
    def __init__(self, name, groupName, settings = None, settingIndex = None,
                 callbacks = {}):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.DRAWER)
        self.settings = settings
        self.settingIndex = settingIndex
        self.callbacks = callbacks
        ## List of ToggleButtons, one per setting.
        self.buttons = []


    ## Generate a row of buttons, one for each possible drawer.
    def makeUI(self, parent):
        if self.callbacks:
            # Nothing to be done here.
            return None
        frame = wx.Frame(parent, title = "Drawers",
                style = wx.RESIZE_BORDER | wx.CAPTION)
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


    ## Let everyone know what the initial drawer is.
    def makeInitialPublications(self):
        if self.callbacks:
            events.publish("drawer change", self)
        else:
            # Calling self.changeDrawer will do it for us, but we can't do
            # that unless we have DrawerSettings to work with.
            self.changeDrawer(self.settings[self.settingIndex])


    ## Let everyone know that the drawer has changed.
    def changeDrawer(self, newSetting):
        if self.callbacks:
            events.publish("drawer change", self)
            return
        self.settingIndex = self.settings.index(newSetting)
        for i, button in enumerate(self.buttons):
            button.setActive(i == self.settingIndex)
        events.publish("drawer change", self)


    ## Get the wavelength for a specified camera name.
    def getWavelengthForCamera(self, cameraName):
        if self.callbacks:
            return self.callbacks['getWavelengthForCamera'](self.name, cameraName)
        return self.settings[self.settingIndex].cameraToWavelength.get(cameraName, None)


    ## Get the dye name for a specified camera name.
    def getDyeForCamera(self, cameraName):
        if self.callbacks:
            return self.callbacks['getDyeForCamera'](self.name, cameraName)
        return self.settings[self.settingIndex].cameraToDye.get(cameraName, '')


    ## Get the color for a specified camera name.
    def getColorForCamera(self, cameraName):
        if self.callbacks:
            return self.callbacks['getColorForCamera'](self.name, cameraName)
        return self.settings[self.settingIndex].cameraToColor[cameraName]


    def addCamera(self, cameraName, filters):
        if not self.settings:
            self.settings = []
            for i, f in enumerate(filters):
                self.settings.append(
                    DrawerSettings('drawer_%d' % (i), [cameraName], [f['dye']],
                                   [DYE_TO_COLOR.get(f['dye'], wavelengthToColor(f['wavelength']))], 
                                   [f['wavelength']]))
        else:
            for i, drawer in enumerate(self.settings):
                if i < len(filters):
                    drawer.update(cameraName,
                              filters[i]['dye'],
                              DYE_TO_COLOR.get(filters[i]['dye'], wavelengthToColor(filters[i]['wavelength'])),
                              filters[i]['wavelength'])
                else:
                    drawer.update(cameraName, 'Empty', ['Empty'], (127,127,127))


## This is a simple container class to describe a single drawer. 
class DrawerSettings:
    ## All parameters except the drawer name are lists, and the lists refer to
    # cameras in the same orders.
    # \param name Name used to refer to the drawer. 
    # \param cameraNames Unique names for each camera. These are the same 
    #        across all drawers.
    # \param dyeNames Names of dyes that roughly correspond to the wavelengths
    #        that the cameras see.
    # \param RGB color tuples (very) roughly corresponding to the wavelengths
    #        that the cameras see.
    # \param wavelengths Numerical wavelengths corresponding to the bandpass
    #        filters in front of the cameras.
    def __init__(self, name, cameraNames, dyeNames, colors, wavelengths):
        self.name = name
        self.cameraNames = cameraNames
        self.dyeNames = dyeNames
        self.colors = colors
        self.wavelengths = wavelengths
        self.cameraToColor = dict(zip(cameraNames, colors))
        self.cameraToDye = dict(zip(cameraNames, dyeNames))
        self.cameraToWavelength = dict(zip(cameraNames, wavelengths))

    def update(self, cameraName, dyeName, color, wavelength):
        for i, camera in enumerate(self.cameraNames):
            if camera == cameraName:
                self.dyeNames[i] = dyeName
                self.colors[i] = color
                self.wavelengths[i] = wavelength
                break
        else:
            # Didn't find the camera name.
            self.cameraNames.append(cameraName)
            self.dyeNames.append(dyeName)
            self.colors.append(color)
            self.wavelengths.append(wavelength)
        self.cameraToColor = dict(zip(self.cameraNames, self.colors))
        self.cameraToDye = dict(zip(self.cameraNames, self.dyeNames))
        self.cameraToWavelength = dict(zip(self.cameraNames, self.wavelengths))