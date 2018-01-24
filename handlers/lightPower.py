import concurrent.futures as futures
import numpy
import time
import wx

import depot
from . import deviceHandler
import events
import gui.guiUtils
import gui.toggleButton
import util.logger
import util.userConfig
import util.threads


## This handler is for light sources where the power of the light can be
# controlled through software.
class LightPowerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - setPower(value): Set power level.
    # - getPower(value): Get current power level.
    # \param minPower Minimum output power in milliwatts.
    # \param maxPower Maximum output power in milliwatts.
    # \param curPower Initial output power.
    # \param color Color to use in the UI to represent this light source.
    # \param isEnabled True iff the handler can be interacted with.
    # \param units Units to use to describe the power; defaults to "mW".

    ## We use a class method to monitor output power by querying hardware.
    # A list of instances. Light persist until exit, so don't need weakrefs.
    _instances = []
    @classmethod
    @util.threads.callInNewThread
    def _updater(cls):
        ## Monitor output power and tell controls to update their display.
        # Querying power status can block while I/O is pending, so we use a
        # threadpool.
        # A map of lights to queries.
        queries = {}
        with futures.ThreadPoolExecutor() as executor:
            while True:
                time.sleep(0.1)
                for light in cls._instances:
                    getPower = light.callbacks['getPower']
                    if light not in queries.keys():
                        queries[light] = executor.submit(getPower)
                    elif queries[light].done():
                        light.lastPower = queries[light].result()
                        light.updateDisplay()
                        queries[light] = executor.submit(getPower)


    def __init__(self, name, groupName, callbacks, wavelength,
            minPower, maxPower, curPower, color, isEnabled = True,
            units = 'mW'):
        # Validation:
        required = set(['getPower', 'setPower'])
        missing = required.difference(callbacks)
        if missing:
            e = Exception('%s %s missing callbacks: %s.' %
                            (self.__class__.__name__,
                             name,
                             ' '.join(missing)))
            raise e

        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.LIGHT_POWER)
        LightPowerHandler._instances.append(self)
        self.wavelength = wavelength
        self.minPower = minPower
        self.maxPower = maxPower
        self.lastPower = curPower
        self.powerSetPoint = None
        self.color = color
        self.isEnabled = isEnabled
        self.units = units
        ## ToggleButton for selecting the current power level.
        self.powerToggle = None
        ## wx.StaticText describing the current power level.
        self.powerText = None

        # The number of levels in the power menu.
        self.numPowerLevels = 20

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        events.subscribe('user login', self.onLogin)

    ## User logged in; load their settings.
    def onLogin(self, username):
        targetPower = util.userConfig.getValue(self.name + '-lightPower', default = 0.01)
        try:
            self.setPower(targetPower)
        except Exception as e:
            util.logger.log.warn("Failed to set prior power level %s for %s: %s" % (targetPower, self.name, e))


    ## Construct a UI consisting of a clickable box that pops up a menu allowing
    # the power to be changed, and a text field showing the current output
    # power.
    def makeUI(self, parent):
        sizer = wx.BoxSizer(wx.VERTICAL)
        button = gui.toggleButton.ToggleButton(inactiveColor = self.color,
                textSize = 12, label = self.name, size = (120, 80),
                parent = parent)
        # Respond to clicks on the button.
        wx.EVT_LEFT_DOWN(button, lambda event: self.makeMenu(parent))
        wx.EVT_RIGHT_DOWN(button, lambda event: self.makeMenu(parent))
        self.powerToggle = button
        sizer.Add(button)
        self.powerText = wx.StaticText(parent, -1,
                '%.1f%s' % (self.lastPower, self.units),
                style = wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE | wx.SUNKEN_BORDER,
                size = (120, 40))
        self.powerToggle.Enable(self.isEnabled)
        # If maxPower is zero or unset, we can not determine the
        # menu entries, so disable powerToggle button.
        if not self.maxPower:
            self.powerToggle.Enable(False)
        self.powerText.Enable(self.isEnabled)
        sizer.Add(self.powerText)
        events.subscribe(self.name + ' update', self.updateDisplay)

        return sizer


    ## Generate a menu at the mouse letting the user select an
    # output power level. They can select from 1 of 20 presets, or input
    # an arbitrary value.
    def makeMenu(self, parent):
        menu = wx.Menu()
        powerDelta = self.maxPower / self.numPowerLevels
        powers = numpy.arange(self.minPower,
                              self.maxPower + powerDelta,
                              powerDelta)
        for i, power in enumerate(powers):
            menu.Append(i + 1, "%d%s" % (min(power, self.maxPower), self.units))
            wx.EVT_MENU(parent, i + 1, lambda event, power = power: self.setPower(power))
        menu.Append(i + 2, '...')
        wx.EVT_MENU(parent, i + 2, lambda event: self.setPowerArbitrary(parent))

        gui.guiUtils.placeMenuAtMouse(parent, menu)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.powerSetPoint


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            try:
                self.setPower(settings[self.name])
            except Exception as e:
                # Invalid power; just ignore it.
                print ("Invalid power for %s: %s" % (self.name, settings.get(self.name, '')))


    ## Toggle accessibility of the handler.
    def setEnabled(self, isEnabled):
        self.isEnabled = isEnabled
        self.powerToggle.Enable(self.isEnabled)
        self.powerText.Enable(isEnabled)


    ## Return True iff we're currently enabled (i.e. GUI is active).
    def getIsEnabled(self):
        return self.isEnabled


    ## Set a new value for minPower.
    def setMinPower(self, minPower):
        self.minPower = minPower


    ## Set a new value for maxPower.
    def setMaxPower(self, maxPower):
        self.maxPower = maxPower


    ## Handle the user selecting a new power level.
    def setPower(self, power):
        if power < self.minPower or power > self.maxPower:
            raise RuntimeError("Tried to set invalid power %f for light %s (range %f to %f)" % (power, self.name, self.minPower, self.maxPower))
        self.callbacks['setPower'](power)
        self.powerSetPoint = power
        util.userConfig.setValue(self.name + '-lightPower', power)
        events.publish(self.name + ' update', self)


    ## Select an arbitrary power output.
    def setPowerArbitrary(self, parent):
        value = gui.dialogs.getNumberDialog.getNumberFromUser(
                parent, "Select a power in milliwatts between 0 and %s:" % self.maxPower,
                "Power (%s):" % self.units, self.powerSetPoint)
        self.setPower(float(value))


    ## Update our laser power display.
    @util.threads.callInMainThread
    def updateDisplay(self, *args, **kwargs):
        # Show current power on the text display, if it exists.
        if self.powerSetPoint and self.lastPower:
            matched = 0.95*self.powerSetPoint < self.lastPower < 1.05*self.powerSetPoint
        else:
            matched = False

        label = ''

        if self.powerSetPoint is None:
            label += "SET: ???%s\n" % (self.units)
        else:
            label += "SET: %.1f%s\n" % (self.powerSetPoint, self.units)

        if self.lastPower is None:
            label += "OUT: ???%s" % (self.units)
        else:
            label += "OUT: %.1f%s" % (self.lastPower, self.units)

        # Update the power label, if it exists.
        if self.powerText:
            self.powerText.SetLabel(label)
            if matched:
                self.powerText.SetBackgroundColour('#99FF99')
            else:
                self.powerText.SetBackgroundColour('#FF7777')

        # Enable or disable the powerToggle button, if it exists.
        if self.powerToggle:
            self.powerToggle.Enable(self.maxPower and self.isEnabled)


    ## Simple getter.
    def getWavelength(self):
        return self.wavelength


    ## Experiments should include the laser power.
    def getSavefileInfo(self):
        return "%s: %.1f%s" % (self.name, self.lastPower, self.units)

# Fire up the status updater.
LightPowerHandler._updater()