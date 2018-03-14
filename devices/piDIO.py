from . import device
import depot
import events
import gui.toggleButton
import collections
import Pyro4
import wx
import threading
import time
import gui.device

## TODO: Clean up code.

class RaspberryPi(device.Device):
    def __init__(self, name, config):
        # self.ipAddress and self.port set by device.Device.__init__
        device.Device.__init__(self, name, config)
        linestring = config.get('lines')
        self.lines = linestring.split(',')
        paths_linesString = config.get('paths')
        self.excitation=[]
        self.excitationMaps=[]
        self.objective=[]
        self.objectiveMaps=[]
        self.emission =[]
        self.emissionMaps=[]

        for path in (paths_linesString.split(';')):
            parts = path.split(':')
            if(parts[0]=='objective'):
                self.objective.append(parts[1])
                self.objectiveMaps.append(parts[2])
            elif (parts[0]=='excitation'):
                self.excitation.append(parts[1])
                self.excitationMaps.append(parts[2])
            elif (parts[0]=='emission'):
                self.emission.append(parts[1])
                self.emmisionMaps.append(parts[2])
            
        self.RPiConnection = None
        ## util.connection.Connection for the temperature sensors.

        self.buttonName='piDIO'

        ## Maps light modes to the mirror settings for those modes, as a list
        #IMD 20140806
        #map paths to flips. 
        self.modeToFlips = collections.OrderedDict()
        for i in range(len(self.excitation)):
            self.modeToFlips[self.excitation[i]] = []
            for flips in self.excitationMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.modeToFlips[self.excitation[i]].append(flipsInt)        
        #map objectives to flips. 
        self.objectiveToFlips = collections.OrderedDict()
        for i in range(len(self.objective)):
            self.objectiveToFlips[self.objective[i]] = []
            for flips in self.objectiveMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.objectiveToFlips[self.objective[i]].append(flipsInt)
                
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
        #set the first excitation mode as the inital state.
        self.setExMode(self.excitation[1])
        #Subscribe to objective change to map new detector path to new pixel sizes via fake objective
        events.subscribe('objective change', self.onObjectiveChange)

    
    ## Generate a column of buttons for setting the light path. Make a window
    # that plots our temperature data.
    def makeUI(self, parent):
        rowSizer=wx.BoxSizer(wx.HORIZONTAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = gui.device.Label(parent, -1, "Excitation path:")
        sizer.Add(label)
        for mode in self.excitation:
            button = gui.toggleButton.ToggleButton( 
                    textSize = 12, label = mode,
                    parent = parent)
            # Respond to clicks on the button.
            button.Bind(wx.EVT_LEFT_DOWN, lambda event, mode = mode: self.setExMode(mode))
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


    ## Flip a mirror down and then up, to ensure that it's in the position
    # we want.
    def flipDownUp(self, index, isUp):
        self.RPiConnection.flipDownUp(index, int(isUp))


    def onObjectiveChange(self, name, pixelSize, transform, offset):
        for flips in self.objectiveToFlips[name]:
            self.flipDownUp(flips[0], flips[1])


    #function to read temperature at set update frequency.
    def updateStatus(self):
        """Runs in a separate thread publish status updates."""
        updatePeriod = 10.0
        temperature = []
        while True:
            if self.RPiConnection:
                try:
                   temperature = self.RPiConnection.get_temperature()
                except:
                    ## There is a communication issue. It's not this thread's
                    # job to fix it. Set temperature to None to avoid bogus
                    # data.
                    temperature = []
            for i in range(len(temperature)):
                events.publish("status update",
                           'RPi',
                           {'temperature'+str(i): temperature[i],})
            time.sleep(updatePeriod)


    ## Debugging function: display a debug window.
    def showDebugWindow(self):
        piOutputWindow(self, parent=wx.GetApp().GetTopWindow()).Show()


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
        for button, line in self.buttonToLine.items():
            if button.getIsActive():
                self.pi.RPiConnection.flipDownUp(line, 1)
            else:
                self.pi.RPiConnection.flipDownUp(line, 0)
