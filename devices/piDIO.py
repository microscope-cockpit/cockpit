import device
import depot
import events
import gui.toggleButton
import util.connection
import collections
import Pyro4
import wx
import re
import threading
import time

from config import config
CLASS_NAME = 'RaspberryPi'
CONFIG_NAME = 'rpi'
#DIO_LINES = ['Objective']
#LINES_PAT = r"(?P<lines>\'\s*\w*\s*\')"



class RaspberryPi(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 10000
        if not self.isActive:
            return
        else:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))
            paths_linesString = config.get(CONFIG_NAME, 'paths')
            excitation=[]
            excitationMaps=[]
            objective=[]
            objectiveMaps=[]
            emission =[]
            emissionMaps=[]
            
            for path in (paths_linesString.split(';')):
                print path
                parts = path.split(':')
                print parts
                if(parts[0]=='objective'):
                    objective.append(parts[1])
                    objectiveMaps.append(parts[2])
                elif (parts[0]=='excitation'):
                    excitation.append(parts[1])
                    excitationMaps.append(parts[2])
                elif (parts[0]=='emission'):
                    emission.append(parts[1])
                    emmisionMaps.append(parts[2])

            print objective,objectiveMaps
            print excitation,excitationMaps
            
        self.RPiConnection = None
        ## util.connection.Connection for the temperature sensors.
		
        self.makeOutputWindow = makeOutputWindow
        self.buttonName='piDIO'

        ## Maps light modes to the mirror settings for those modes, as a list
        #IMD 20140806
        self.modeToFlips = collections.OrderedDict()
        for i in xrange(len(excitation)):
            self.modeToFlips[excitation[i]] = []
            for flips in excitationMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.modeToFlips[excitation[i]].append(flipsInt)        

        self.lightPathButtons = []
        ## Current light path mode.
        self.curExMode = None

        # A thread to publish status updates.
        # This reads temperature updates from the RaspberryPi
        self.statusThread = threading.Thread(target=self.updateStatus)
        self.statusThread.Daemon = True
        self.statusThread.start()
 

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
        if (name=='10x'):
            self.flipDownUp(0, 1)
            self.flipDownUp(1, 0)
        elif (name=='60xwater'):
            self.flipDownUp(0, 0)
            self.flipDownUp(1, 1)
        else: #default behaviour, mapping objective
            self.flipDownUp(0, 1)
            self.flipDownUp(1, 0)
        print "piDIO objective change"
		
    #function to read temperature at set update frequency. 
    def updateStatus(self):
        """Runs in a separate thread publish status updates."""
        updatePeriod = 10.0
        temperature = None
        while True:
            if self.RPiConnection:
                try:
                   temperature = self.RPiConnection.get_temperature()
                except:
                    ## There is a communication issue. It's not this thread's
                    # job to fix it. Set temperature to None to avoid bogus
                    # data.
                    temperature = None
            events.publish("status update",
                           'RPi',
                           {'temperature': temperature,})
            time.sleep(updatePeriod)



## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class piOutputWindow(wx.Frame):
    def __init__(self, piDIO, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## piDevice instance.
        self.pi = piDIO
        # Contains all widgets.
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 4, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        # Set up the digital lineout buttons.
        for i in range(len(piDIO.lines)) :
            button = gui.toggleButton.ToggleButton(
                    parent = panel, label = str(piDIO.lines[i]),
                    activateAction = self.toggle,
                    deactivateAction = self.toggle,
                    size = (140, 80))
            buttonSizer.Add(button, 1, wx.EXPAND)
            self.buttonToLine[button] = i
        mainSizer.Add(buttonSizer)

        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())


    ## One of our buttons was clicked; update the DSP's output.
    def toggle(self):
        output = 0
        for button, line in self.buttonToLine.iteritems():
            if button.getIsActive():
                self.pi.RPiConnection.flipDownUp(line, 1)
            else:
                self.pi.RPiConnection.flipDownUp(line, 0)


## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    piOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    
