import wx

import depot
from . import deviceHandler
import events

import gui.dialogs.getNumberDialog
import gui.guiUtils
import gui.toggleButton
import util.threads

## List of exposure times to allow the user to set.
EXPOSURE_TIMES = [1, 5] + list(range(10, 100, 10)) + list(range(100, 1100, 100))

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
    # \param trigHandler: Optional. Sets up an auxilliary trigger source.
    # \param trigLine: Optional. May be required by aux. trig. source.

    ## Shortcuts to decorators defined in parent class.
    reset_cache = deviceHandler.DeviceHandler.reset_cache
    cached = deviceHandler.DeviceHandler.cached

    ## Keep track of shutters in class variables.
    __shutterToLights = {} # 1:many
    __lightToShutter = {} # 1:1
    @classmethod
    def addShutter(cls, shutter, lights=[]):
        cls.__shutterToLights[shutter] = set(lights)
        for l in lights:
            cls.__lightToShutter[l] = shutter


    def __init__(self, name, groupName, callbacks, wavelength, exposureTime,
                 trigHandler=None, trigLine=None):
        # Note we assume all light sources are eligible for experiments.
        # However there's no associated callbacks for a light source.
        deviceHandler.DeviceHandler.__init__(self, name, groupName, True, 
                callbacks, depot.LIGHT_TOGGLE)
        self.wavelength = float(wavelength or 0)
        self.defaultExposureTime = exposureTime
        # Current enabled state
        self.state = deviceHandler.STATES.disabled
        ## A text widget describing our exposure time and providing a
        # menu for changing it.
        # TODO - separate handler from ui; exposureTime is a widget, not a parameter.
        self.exposureTime = None
        # Set up trigger handling.
        if trigHandler and trigLine:
            trigHandler.registerDigital(self, trigLine)
            self.triggerNow = lambda: trigHandler.triggerDigital(self)
            if 'setExposing' not in callbacks:
                cb = lambda name, state: trigHandler.setDigital(trigLine, state)
                callbacks['setExposing'] = cb
        else:
            self.triggerNow = lambda: None


        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        events.subscribe('light exposure update', self.setLabel)

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


    ## Turn the laser on, off, or set continuous exposure.
    def setEnabled(self, setState):
        if self.state == deviceHandler.STATES.constant != setState:
            if 'setExposing' in self.callbacks:
                self.callbacks['setExposing'](self.name, False)

        if setState == deviceHandler.STATES.constant:
            if self.state == setState:
                # Turn off the light
                self.callbacks['setEnabled'](self.name, False)
                # Update setState since used to set self.state later
                setState = deviceHandler.STATES.disabled
                events.publish('light source enable', self, False)
            else:
                # Turn on the light continuously.
                self.callbacks['setEnabled'](self.name, True)
                if 'setExposing' in self.callbacks:
                    self.callbacks['setExposing'](self.name, True)
                # We indicate that the light source is disabled to prevent
                # it being switched off by an exposure, but this event is
                # used to update controls, so we need to chain it with a
                # manual update.
                events.oneShotSubscribe('light source enable',
                                        lambda *args: self.notifyListeners(self, setState))
                events.publish('light source enable', self, False)
        elif setState == deviceHandler.STATES.enabled:
            self.callbacks['setEnabled'](self.name, True)
            events.publish('light source enable', self, True)
        else:
            self.callbacks['setEnabled'](self.name, False)
            events.publish('light source enable', self, False)
        self.state = setState


    ## Return True if we're enabled, False otherwise.
    def getIsEnabled(self):
        return self.state == deviceHandler.STATES.enabled


    ## Make the UI for our light: a toggle button for whether or not to use
    # us, and a widget for setting the exposure time.
    def makeUI(self, parent):
        # Sequester to our own panel so that we don't propagate menu
        # events with possibly-redundant IDs to the parent.
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Split the name across multiple lines.
        label = ['']
        if self.name.endswith('toggle'):
            name = self.name[0:-7]
        else:
            name = self.name
        for word in name.split(' '):
            if len(label[-1] + word) > 10:
                label.append('')
            label[-1] += word + ' '
        label = "\n".join(label)
        button = gui.device.EnableButton(parent=panel,
                                                  leftAction=self.toggleState,
                                                  rightAction=self.setExposing,
                                                  prefix=label)
        sizer.Add(button)
        self.addListener(button)
        helpText = "Left-click to enable for taking images."
        if 'setExposing' in self.callbacks:
            # Light source can also be just turned on and left on.
            helpText += "\nRight-click to leave on indefinitely."
        button.SetToolTip(wx.ToolTip(helpText))
        self.exposureTime = gui.toggleButton.ToggleButton(
                label = '', parent = panel, size = BUTTON_SIZE)
        self.exposureTime.Bind(wx.EVT_LEFT_DOWN,
                lambda event: self.makeMenu(panel))
        self.setLabel()
        sizer.Add(self.exposureTime)
        panel.SetSizerAndFit(sizer)
        return panel


    ## Set the light source to continuous exposure, if we have that option.
    @util.threads.callInNewThread
    def setExposing(self, args):
        if not self.enableLock.acquire(False):
            return
        self.notifyListeners(self, deviceHandler.STATES.enabling)
        try:
            self.setEnabled(deviceHandler.STATES.constant)
        except Exception as e:
            self.notifyListeners(self, deviceHandler.STATES.error)
            raise Exception('Problem encountered en/disabling %s:\n%s' % (self.name, e))
        finally:
            self.enableLock.release()


    ## Return True iff we are in continuous-exposure mode. We use the color
    # of our button as the indicator for that state.
    def getIsExposingContinuously(self):
        return self.state == deviceHandler.STATES.constant


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
    def setLabel(self, source=None):
        if source is not None and source != self:
            return
        value = self.getExposureTime()
        if int(value) == value:
            label = '%dms' % value
        else:
            # Show some decimal points.
            label = '%.3fms' % value
        self.exposureTime.SetLabel(label)


    ## Set a new exposure time, in milliseconds.
    @reset_cache
    def setExposureTime(self, value, outermost=True):
        ## Set the exposure time on self and update that on lights
        # that share the same shutter if this is the outermost call.
        # \param value: new exposure time
        # \param outermost: flag indicating that we should update others.
        self.callbacks['setExposureTime'](self.name, value)
        # Publish event to update control labels.
        events.publish('light exposure update', self)
        # Update exposure times for lights that share the same shutter.
        s = self.__class__.__lightToShutter.get(self, None)
        if s and outermost:
            if hasattr(s, 'setExposureTime'):
                s.setExposureTime(value)
            for other in self.__class__.__shutterToLights[s].difference([self]):
                other.setExposureTime(value, outermost=False)
                events.publish('light exposure update', other)

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

