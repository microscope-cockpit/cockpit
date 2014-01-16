import depot
import device
import events
import gui.toggleButton
import handlers.genericPositioner
import microManager
import util.userConfig

import wx

CLASS_NAME = 'TIRFMirrorDevice'



## This controls the TIRF mirror position.
class TIRFMirrorDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # We must initialize after the microManager module.
        self.priority = 1000
        ## MMCorePy object, same as in the microManager module.
        self.core = None
        ## Current position of the TIRF mirror.
        self.curPosition = None
        ## gui.toggleButton for [de]activating TIRF.
        self.activeButton = None
        ## wx.TextCtrl for setting the current position.
        self.positionText = None
        ## Maps lightsource wavelengths to the positions we use for them.
        self.wavelengthToPosition = {}

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)


    def initialize(self):
        mmDevice = depot.getDevice(microManager)
        self.core = mmDevice.getCore()
        self.curPosition = self.core.getProperty('TITIRF', 'Position')
        events.subscribe('light source enable', self.onLightEnable)
        self.wavelengthToPosition = util.userConfig.getValue(
                'TIRF mirror positions', default = {}, isGlobal = True)
        

    def getHandlers(self):
        return [handlers.genericPositioner.GenericPositionerHandler(
                'TIRF mirror position', 'miscellaneous', True,
                {
                    'moveAbsolute': self.moveAbsolute,
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition,
                    'getMovementTime': self.getMovementTime,
                }
            )
        ]


    def makeUI(self, parent):
        curPosition = self.core.getProperty('TITIRF', 'Position')
        panel = wx.Panel(parent, style = wx.BORDER_SUNKEN)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        rowSizer.Add(wx.StaticText(panel, -1, 'TIRF mirror:'), 1, wx.EXPAND | wx.HORIZONTAL)
        self.activeButton = gui.toggleButton.ToggleButton(parent = panel,
                textSize = 10, activateAction = self.toggleTirf,
                deactivateAction = self.toggleTirf,
                activeLabel = 'Enabled', inactiveLabel = 'Disabled',
                size = (100, -1))
        self.activeButton.setActive(
                self.core.getProperty('TITIRF', 'Mirror') == 'In')
        rowSizer.Add(self.activeButton)
        sizer.Add(rowSizer)

        self.positionText = wx.TextCtrl(panel, -1, size = (80, -1),
                style = wx.TE_PROCESS_ENTER)
        self.positionText.Bind(wx.EVT_TEXT_ENTER, self.onText)
        self.positionText.SetValue(curPosition)
        sizer.Add(self.positionText, 1, wx.EXPAND | wx.HORIZONTAL | wx.ALIGN_CENTER)
        # Max position is experimentally derived.
        self.positionSlider = wx.Slider(panel, -1, int(curPosition),
                0, 70000, size = (200, -1), style = wx.SL_HORIZONTAL)
        self.positionSlider.Bind(wx.EVT_SCROLL, self.onSlider)
        self.positionSlider.SetValue(int(curPosition))
        sizer.Add(self.positionSlider)
        panel.SetSizer(sizer)
        panel.Fit()
        panel.SetSize((240, 50))
        return panel


    ## User has clicked the toggle-TIRF button.
    def toggleTirf(self, *args):
        self.core.setProperty('TITIRF', 'Mirror',
                ['Out', 'In'][self.activeButton.getIsActive()])


    ## User has manipulated the text box.
    def onText(self, event):
        position = int(self.positionText.GetValue())
        self.moveAbsolute(None, position)


    ## User has manipulated the slider.
    def onSlider(self, event):
        position = self.positionSlider.GetValue()
        self.moveAbsolute(None, position)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings['TIRF mirror'] = [self.curPosition, self.activeButton.getIsActive()]


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if 'TIRF mirror' in settings:
            position, isActive = settings['TIRF mirror']
            self.moveAbsolute(None, position)
            self.activeButton.setActive(isActive)
            

    ## Move the mirror to the specified position.
    def moveAbsolute(self, name, position):
        # Sanity check.
        position = int(position)
        self.core.setProperty('TITIRF', 'Position', position)
        self.curPosition = position
        # Check if we only have 1 light active; if so, update our config.
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        numActive = sum([(l.getIsEnabled() and 'LED' not in l.name) for l in allLights])
        if numActive == 1:
            for light in allLights:
                if light.getIsEnabled():
                    self.wavelengthToPosition[light.wavelength] = self.curPosition
                    break
            util.userConfig.setValue('TIRF mirror positions',
                    self.wavelengthToPosition, isGlobal = True)
        self.positionText.SetValue(str(self.curPosition))
        self.positionSlider.SetValue(self.curPosition)


    ## Move the mirror by the given delta.
    def moveRelative(self, name, delta):
        self.moveAbsolute(self.curPosition + delta)


    ## Return the current position.
    def getPosition(self):
        return self.curPosition


    ## Get the movement time and stabilization time for a given mirror motion.
    # These values are made up.
    def getMovementTime(self, name, start, stop):
        return (1, 0)


    ## A light source was enabled or disabled. If we're running only one
    # light source currently, then check if we have a stored position for
    # that source (since the TIRF mirror position is slightly different for
    # each light source).
    def onLightEnable(self, handler, isEnabled):
        if (not isEnabled) or 'LED' in handler.name:
            return
        # Skip if we have multiple active light sources.
        allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        numActive = sum([(l.getIsEnabled() and 'LED' not in handler.name) for l in allLights])
        if numActive != 1:
            return
        if handler.wavelength not in self.wavelengthToPosition:
            # Set a new default of our current position.
            self.wavelengthToPosition[handler.wavelength] = self.curPosition
        # This will also write out our config.
        self.moveAbsolute(None, self.wavelengthToPosition[handler.wavelength])
            
    
