import device
import depot
import events
import gui.toggleButton
import util.connection
import collections
import Pyro4
import wx

from config import config
CLASS_NAME = 'RaspberryPi'
CONFIG_NAME = 'RPi'



class RaspberryPi(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 10000
        if not self.isActive:
            return
        else:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))
        self.RPiConnection = None
        ## util.connection.Connection for the temperature sensors.

        ## Maps light modes to the mirror settings for those modes, as a list
        #IMD 20140806
        self.modeToFlips = collections.OrderedDict()
        self.modeToFlips['Conventional'] = [(0, True)]
        self.modeToFlips['Structured Illumination'] = [(0, False)]

        self.lightPathButtons = []
        ## Current light path mode.
        self.curExMode = None

        ## Connect to the remote program, and set widefield mode.
    def initialize(self):
        self.RPiConnection = Pyro4.Proxy('PYRO:%s@%s:%d' % ('pi', self.ipAddress, self.port))

    ## Try to switch to widefield mode.
    def finalizeInitialization(self):
        self.setExMode('Conventional')
        #Subscribe to objective change to map new detector path to new pixel sizes via fake objective
        events.subscribe('objective change', self.onObjectiveChange)


    ## Ensure the room light status is shown.
    def makeInitialPublications(self):
#        events.publish('new status light', 'room light', '')
#        self.receiveLightData('test', not self.lightConnection.connection.getIsLightOn())
        
        pass

    ## Generate a column of buttons for setting the light path. Make a window
    # that plots our temperature data.
    def makeUI(self, parent):

        rowSizer=wx.BoxSizer(wx.HORIZONTAL)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(parent, -1, "Excitation path:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        for mode in ['Conventional', 'Structured Illumination']:
            button = gui.toggleButton.ToggleButton( 
                    textSize = 12, label = mode, size = (180, 50), 
                    parent = parent)
            # Respond to clicks on the button.
            wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setExMode(mode))
            sizer.Add(button)
            self.lightPathButtons.append(button)
            if mode == self.curExMode:
                button.activate()
        rowSizer.Add(sizer)
        return rowSizer


    ## Set the light path to the specified mode.
    def setExMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.lightPathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curExMode = mode



    def setDetMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.detPathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curDetMode = mode
    #IMD 20150129 - flipping buttons for detection path also changes objective
    # set correct pixel size and image orientation
        objectiveHandler = depot.getHandlerWithName('objective')
        if mode == 'with AO & 85 nm pixel size' :
            if (objectiveHandler.curObjective != '63x85nm') :
                objectiveHandler.changeObjective('63x85nm')
                print "Change objective 85 nm pixel"
        elif mode == 'w/o AO & 209 nm pixel size' :
            if (objectiveHandler.curObjective != '63x209nm') :
                objectiveHandler.changeObjective('63x209nm')
                print "Change objective 209 nm pixel"
        


         

    ## Flip a mirror down and then up, to ensure that it's in the position
    # we want.
    def flipDownUp(self, index, isUp):
        self.RPiConnection.flipDownUp(index, int(isUp))


    def onObjectiveChange(self, name, pixelSize, transform, offset):
        #       if (name=='63x85nm'):
        #           self.setDetMode('with AO & 85 nm pixel size')
#       elif (name=='63x209nm'):
#           self.setDetMode('w/o AO & 209 nm pixel size')
        print "pi-DIO objective change"
