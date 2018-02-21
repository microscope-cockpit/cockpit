import wx

import depot
import deviceHandler
import events

import gui.dialogs.getNumberDialog
import gui.guiUtils
import gui.toggleButton

## List of exposure times to allow the user to set.
EXPOSURE_TIMES = [1, 5] + range(10, 100, 10) + range(100, 1100, 100)

## Color to use for light sources that are in continuous exposure mode.
CONTINUOUS_COLOR = (255, 170, 0)

## Size of the button we make in the UI.
BUTTON_SIZE = (120, 40)



## This handler is for lightsource toggle buttons and exposure time settings,
# to control if a given illumination source is currently active (and for how
# long).
class LightHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions: 
    # - setEnabled(name, value): Turn this light source on or off.
    # - setExposureTime(name, value): Set the exposure time for this light,
    #   in milliseconds.
    # - getExposureTime(name, value): Get the current exposure time for this
    #   light, in milliseconds.
    # - setExposing(name, isOn): Optional. Sets the light on/off continuously
    #   (i.e. without regard for what the camera(s) are doing). 
    # \param wavelength Wavelength of light the source emits, if appropriate.
    # \param exposureTime Default exposure time.

    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    def __init__(self, name, groupName, callbacks, wavelength, exposureTime):
        # Note we assume all light sources are eligible for experiments.
        # However there's no associated callbacks for a light source.
        deviceHandler.DeviceHandler.__init__(self, name, groupName, True, 
                callbacks, depot.LIGHT_TOGGLE)
        self.wavelength = wavelength
        self.defaultExposureTime = exposureTime
        ## Our GUI button, which we also use as a proxy for if we're currently
        # active.
        self.activeButton = None
        ## A text widget describing our exposure time and providing a
        # menu for changing it.
        self.exposureTime = None

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        events.subscribe('laser exposure update', self.setLabel)

    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = {
            'isEnabled': self.getIsEnabled(),
            'exposureTime': self.getExposureTime()}


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            self.setExposureTime(settings[self.name]['exposureTime'])
            self.setEnabled(settings[self.name]['isEnabled'])


    ## Handle the laser being turned on/off by the user clicking on our button.
    def toggle(self, isOn):
        if self.getIsExposingContinuously() and isOn:
            # Actually we're already active; disable continuous-exposure
            # mode instead.
            self.callbacks['setExposing'](self.name, False)
            # This will call toggle again...
            wx.CallAfter(self.activeButton.setActive, False)
        else:
            self.callbacks['setEnabled'](self.name, isOn)
            events.publish('light source enable', self, isOn)


    ## Turn the laser on and off, by manually toggling the button.
    def setEnabled(self, value):
        if self.getIsExposingContinuously():
            # Disable continuous activation first.
            self.toggle(True)
        self.activeButton.setActive(value)
        events.publish('light source enable', self, value)
       

    ## Return True if we're enabled, False otherwise.
    def getIsEnabled(self):
        return self.activeButton.getIsActive()


    ## Make the UI for our light: a toggle button for whether or not to use
    # us, and a widget for setting the exposure time.
    def makeUI(self, parent):
        # Sequester to our own panel so that we don't propagate menu
        # events with possibly-redundant IDs to the parent.
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Split the name across multiple lines.
        label = ['']
        for word in self.name.split(' '):
            if len(label[-1] + word) > 10:
                label.append('')
            label[-1] += word + ' '
        label = "\n".join(label)
        self.activeButton = gui.toggleButton.ToggleButton(
                activateAction = lambda: self.toggle(True),
                deactivateAction = lambda: self.toggle(False),
                label = label, parent = panel,
                size = (BUTTON_SIZE[0], -1))
        self.activeButton.Bind(wx.EVT_RIGHT_DOWN, lambda event: self.setExposing())
        helpText = "Left-click to enable for taking images."
        if 'setExposing' in self.callbacks:
            # Light source can also be just turned on and left on.
            helpText += "\nRight-click to leave on indefinitely."
        self.activeButton.SetToolTip(wx.ToolTip(helpText))
        sizer.Add(self.activeButton)
        self.exposureTime = gui.toggleButton.ToggleButton(
                label = '', parent = panel, size = BUTTON_SIZE)
        self.exposureTime.Bind(wx.EVT_LEFT_DOWN,
                lambda event: self.makeMenu(panel))
        self.setLabel()
        sizer.Add(self.exposureTime)
        panel.SetSizerAndFit(sizer)
        return panel


    ## Set the light source to continuous exposure, if we have that option.
    # \param value True for on, False for off, None for toggle
    def setExposing(self, value = None):
        if 'setExposing' in self.callbacks:
            isCurrentlyOn = self.getIsExposingContinuously()
            if value is None:
                value = not isCurrentlyOn
            if bool(value) == isCurrentlyOn:
                # Nothing to do.
                return
            self.callbacks['setExposing'](self.name, value)
            if isCurrentlyOn:
                # Turn it off.
                self.activeButton.deactivate()
            else:
                # Set the light source to show as continuously on...
                self.activeButton.SetBackgroundColour(CONTINUOUS_COLOR)
                self.activeButton.Refresh()
                # ...but don't mark it as enabled, so it doesn't
                # get used and then turned off when an image is taken.


    ## Return True iff we are in continuous-exposure mode. We use the color
    # of our button as the indicator for that state.
    def getIsExposingContinuously(self):
        color = self.activeButton.GetBackgroundColour()
        return color == CONTINUOUS_COLOR


    ## Make a menu to let the user select the exposure time.
    def makeMenu(self, parent):
        menu = wx.Menu()
        for i, value in enumerate(EXPOSURE_TIMES):
            menu.Append(i + 1, str(value))
            wx.EVT_MENU(parent, i + 1, lambda event, value = value: self.setExposureTime(value))
        menu.Append(len(EXPOSURE_TIMES) + 1, '...')
        wx.EVT_MENU(parent, len(EXPOSURE_TIMES) + 1, lambda event: self.setCustomExposureTime(parent))
        gui.guiUtils.placeMenuAtMouse(parent, menu)


    ## Pop up a dialog to let the user input a custom exposure time.
    def setCustomExposureTime(self, parent):
        value = gui.dialogs.getNumberDialog.getNumberFromUser(
                parent, "Input an exposure time:",
                "Exposure time (ms):", self.getExposureTime())
        self.setExposureTime(float(value))


    ## Update the label we show for our exposure time.
    def setLabel(self):
        label = None
        value = self.getExposureTime()
        if int(value) == value:
            label = '%dms' % value
        else:
            # Show some decimal points.
            label = '%.3fms' % value
        self.exposureTime.SetLabel(label)


    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, value):
        self.callbacks['setExposureTime'](self.name, value)
        events.publish('laser exposure update')
        self.setLabel()


    ## Get the current exposure time, in milliseconds.
    @cached
    def getExposureTime(self):
        return self.callbacks['getExposureTime'](self.name)


    ## Simple getter.
    @cached
    def getWavelength(self):
        return self.wavelength


    ## Let them know what wavelength we are.
    def getSavefileInfo(self):
        return str(self.wavelength)

