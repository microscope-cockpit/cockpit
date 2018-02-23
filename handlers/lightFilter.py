import decimal
import wx

import depot
from . import deviceHandler

import events
import gui.guiUtils
import gui.toggleButton
import util.userConfig


## This handler is for light filters, which control the percentage of light
# from a given light source reaches the sample.
class LightFilterHandler(deviceHandler.DeviceHandler):
    ## callbacks should fill in the following functions:
    # - setPosition(name, index): Set the filter's position.
    # \param filterAmounts An array of filtration amounts. If this is a 
    #        global filter (affecting all light sources), then this is a 1D
    #        array; otherwise it is an ND array where the first (N-1) indices
    #        are the positions of the global filters. 
    # \todo Multiple global filters has NOT BEEN TESTED. But it should work.
    # \param color Color to use in the UI to represent this light source.
    # \param curPosition Initial position of the filter.
    # \param numGlobals Number of global filters.
    # \param globalIndex Which global filter this is. None if this is not
    #        a global filter.
    def __init__(self, name, groupName, callbacks, wavelength, 
            filterAmounts, color, curPosition, numGlobals, globalIndex = None):
        deviceHandler.DeviceHandler.__init__(self, name, groupName,
                False, callbacks, depot.LIGHT_FILTER)
        self.wavelength = wavelength
        self.filterAmounts = filterAmounts
        self.color = color
        self.globalIndex = globalIndex

        ## List of indices of the global filter.
        self.globalPositions = [0 for i in range(numGlobals)]
        ## Current position of the filter
        self.curPosition = curPosition
        ## wx.StaticText describing the current filtration amount.
        self.filterText = None

        if self.globalIndex is None:
            events.subscribe('global filter change', self.onGlobalFilterChange)

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        events.subscribe('user login', self.onLogin)


    ## Publish global filter position, if relevant.
    def makeInitialPublications(self):
        if self.globalIndex is not None:
            events.publish('global filter change', 
                    self.globalIndex, self.curPosition)


    ## User logged in; load their settings.
    def onLogin(self, username):
        self.selectPosition(util.userConfig.getValue(self.name + '-filterPosition', default = 0))


    ## Construct a UI consisting of a clickable box that pops up a menu allowing
    # the filter position to be changed, and two text fields beneath it to 
    # show the current position and actual filtration amount.
    def makeUI(self, parent):
        sizer = wx.BoxSizer(wx.VERTICAL)
        button = gui.toggleButton.ToggleButton(inactiveColor = self.color, 
                textSize = 12, label = self.name, size = (120, 80), 
                parent = parent)
        # Respond to clicks on the button.
        wx.EVT_LEFT_DOWN(button, self.makeMenu)
        wx.EVT_RIGHT_DOWN(button, self.makeMenu)
        # This control has a special right-click behaviour, so don't pass
        # up EVT_CONTEXT_MENU CommandEvents.
        button.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)
        sizer.Add(button)
        self.filterText = wx.StaticText(parent, -1, '%.3f' % 1,
                style = wx.ALIGN_CENTRE_HORIZONTAL | wx.ST_NO_AUTORESIZE | wx.SUNKEN_BORDER,
                size = (120, 40))
        sizer.Add(self.filterText)
        return sizer


    ## Generate a menu at the mouse letting the user select one of our 
    # filter positions.
    def makeMenu(self, event):
        eventObject = event.GetEventObject()

        action = lambda event: self.selectPosition(event.GetId() - 1)

        menu = wx.Menu()
        for i, filterAmount in enumerate(self.getFiltrations()):
            menu.AppendCheckItem(i + 1, "%s%%" % (filterAmount * 100))
            menu.Check(i + 1, self.curPosition == i)
            wx.EVT_MENU(eventObject, i + 1, action)

        gui.guiUtils.placeMenuAtMouse(eventObject, menu)


    ## Handle the user selecting a position for the filter.
    def selectPosition(self, index):
        self.curPosition = index
        if self.globalIndex is not None:
            events.publish('global filter change', 
                    self.globalIndex, self.curPosition)
        self.callbacks['setPosition'](self.name, index)
        util.userConfig.setValue(self.name + '-filterPosition', index)
        wx.CallAfter(self.updateText)


    ## Update our text displays to indicate our current filter amounts.
    def updateText(self):
        filtration = self.getFiltrations()[self.curPosition]
        self.filterText.SetLabel(str(filtration))


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings[self.name] = self.curPosition


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if self.name in settings:
            try:
                self.selectPosition(settings[self.name])
            except Exception as e:
                print ("Invalid filter position for %s: %s" % (self.name, settings.get(self.name, '')))


    ## Get the available filtrations, given the current global positions.
    def getFiltrations(self):
        filtrations = self.filterAmounts
        for globalFilter in self.globalPositions:
            filtrations = filtrations[globalFilter]
        return filtrations


    ## React to a global filter moving.
    def onGlobalFilterChange(self, globalIndex, position):
        self.globalPositions[globalIndex] = position
        wx.CallAfter(self.updateText)


    ## Return True if this is a global filter.
    def getIsGlobal(self):
        return self.globalIndex is not None


    ## Simple getter.
    def getWavelength(self):
        return self.wavelength


    ## Experiments should include the filter settings.
    def getSavefileInfo(self):
        return "%s: %s" % (self.name, self.filterText.GetLabel())
