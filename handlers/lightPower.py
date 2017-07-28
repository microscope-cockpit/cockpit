import numpy
import wx

import depot
import deviceHandler
import events

import gui.guiUtils
import gui.toggleButton
import util.logger
import util.userConfig



## This handler is for light sources where the power of the light can be
# controlled through software.
class LightPowerHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - setPower(name, value): Set the filter's position.
    # \param minPower Minimum output power in milliwatts.
    # \param maxPower Maximum output power in milliwatts.
    # \param curPower Initial output power.
    # \param color Color to use in the UI to represent this light source.
    # \param isEnabled True iff the handler can be interacted with.
    # \param units Units to use to describe the power; defaults to "mW".
    def __init__(self, name, groupName, callbacks, wavelength,
            minPower, maxPower, curPower, color, isEnabled = True,
            units = 'mW'):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.LIGHT_POWER)
        self.wavelength = wavelength
        self.minPower = minPower
        self.maxPower = maxPower
        self.curPower = curPower
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
        except Exception, e:
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
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: self.makeMenu(parent))
        button.Bind(wx.EVT_RIGHT_DOWN, lambda event: self.makeMenu(parent))
        self.powerToggle = button
        sizer.Add(button)
        self.powerText = wx.StaticText(parent, -1,
                '%.1f%s' % (self.curPower, self.units),
                style = wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE | wx.SUNKEN_BORDER,
                size = (120, 40))
        self.powerToggle.Enable(self.isEnabled)
        # If maxPower is zero or unset, we can not determine the
        # menu entries, so disable powerToggle button.
        if not self.maxPower:
            self.powerToggle.Enable(False)
        self.powerText.Enable(self.isEnabled)
        sizer.Add(self.powerText)
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
            parent.Bind(wx.EVT_MENU,
                        lambda event, power = power: self.setPower(power),
                        id=i + 1)
        menu.Append(i + 2, '...')
        parent.Bind(wx.EVT_MENU, lambda event: self.setPowerArbitrary(parent),
                    id= i + 2)

        gui.guiUtils.placeMenuAtMouse(parent, menu)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.curPower


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            try:
                self.setPower(settings[self.name])
            except Exception, e:
                # Invalid power; just ignore it.
                print "Invalid power for %s: %s" % (self.name, settings.get(self.name, ''))


    ## Toggle accessibility of the handler.
    def setEnabled(self, isEnabled):
        self.isEnabled = isEnabled
        self.powerToggle.Enable(self.isEnabled)
        self.powerText.Enable(isEnabled)


    ## Return True iff we're currently enabled (i.e. GUI is active).
    def getIsEnabled(self):
        return self.isEnabled


    ## Set a new value for curPower.
    def setCurPower(self, curPower):
        self.curPower = curPower
        util.userConfig.setValue(self.name + '-lightPower', curPower)
        self.updateDisplay()


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
        self.callbacks['setPower'](self.name, power)


    ## Select an arbitrary power output.
    def setPowerArbitrary(self, parent):
        value = gui.dialogs.getNumberDialog.getNumberFromUser(
                parent, "Select a power in milliwatts between 0 and %s:" % self.maxPower,
                "Power (%s):" % self.units, self.curPower)
        self.setPower(float(value))


    ## Update our laser power display.
    def updateDisplay(self):
        #Publish a power update event
        events.publish('laser power update',self)
        # Show current power on the text display, if it exists.
        if self.powerSetPoint and self.curPower:
            matched = 0.95*self.powerSetPoint < self.curPower < 1.05*self.powerSetPoint
        else:
            matched = False

        label = ''

        if self.powerSetPoint is None:
            label += "SET: ???%s\n" % (self.units)
        else:
            label += "SET: %.1f%s\n" % (self.powerSetPoint, self.units)

        if self.curPower is None:
            label += "OUT: ???%s" % (self.units)
        else:
            label += "OUT: %.1f%s" % (self.curPower, self.units)

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
        return "%s: %.1f%s" % (self.name, self.curPower, self.units)
