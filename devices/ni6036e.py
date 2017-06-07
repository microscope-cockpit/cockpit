import device
import depot
import events
import gui.toggleButton
import util.connection
import threading

import collections
import matplotlib
matplotlib.use('WXAgg')
import numpy
import pylab
import Pyro4
import wx

from config import config
CLASS_NAME = 'NI6036eDevice'
CONFIG_NAME = 'NIcard'



class NI6036eDevice(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        if not self.isActive:
            return
        else:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))

            #get DIO control lines from config file
            linestring = config.get(CONFIG_NAME, 'lines')
            self.lines = linestring.split(',')
            #Get microscope paths from config file.
            paths_linesString = config.get(CONFIG_NAME, 'paths')
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
            
            #IMD 20150208 comment out to make this work, need to fix
            # self.PLOT_COLORS = config.get(CONFIG_NAME, 'PLOT_COLORS')
            # self.LEGENDS = config.get(CONFIG_NAME, 'LEGENDS')
            # self.DATA_REORDER = config.get(CONFIG_NAME, 'DATA_REORDER')
            
            #IMD 20150208 this should go into config file but dont understand how t define an array there
            #this stuff just gets set as a raw string. 
            self.PLOT_COLORS = ['r', 'g', 'b', 'c', 'm', 'y', 'k']
            ## Labels to use for lines in the plot.
            self.LEGENDS = ['X-nano', 'Y-nano', 'Z-nano', 'Stage', 'Block', 'Room']
            ## How we rearrange the incoming data so that it displays e.g. the nanomover
            # sensors in order.
            #DATA_REORDER = [1, 2, 4, 0, 5, 3]
            self.DATA_REORDER = [0,1]


        self.makeOutputWindow = makeOutputWindow
        self.buttonName='ni6036e'

        device.Device.__init__(self)
        # We want to delay initialization until after the power buttons system
        # is active.
        self.priority = 50
        ## Pyro4.Proxy for the "NI" portion of the program (mirror flips and
        # a few utility functions).
        self.niConnection = None
        ## util.connection.Connection for the temperature sensors.
        self.temperatureConnection = None
        ## util.connection.Connection for the light sensor.
        self.lightConnection = None
        
        ## Maps light modes to the mirror settings for those modes, as a list
        #IMD 20140806
        #map paths to flips. 
        self.modeToFlips = collections.OrderedDict()
        for i in xrange(len(self.excitation)):
            self.modeToFlips[self.excitation[i]] = []
            for flips in self.excitationMaps[i].split('|'):
                flipsList=flips.split(',')
                flipsInt=[int(flipsList[0]),int(flipsList[1])]
                self.modeToFlips[self.excitation[i]].append(flipsInt)        
        #map objectives to flips. 
        self.objectiveToFlips = collections.OrderedDict()
        for i in xrange(len(self.objective)):
            print self.objectiveMaps
            self.objectiveToFlips[self.objective[i]] = []
            if(self.objectiveMaps[i]):
                for flips in self.objectiveMaps[i].split('|'):
                    flipsList=flips.split(',')
                    flipsInt=[int(flipsList[0]),int(flipsList[1])]
                    self.objectiveToFlips[self.objective[i]].append(flipsInt)
                
        self.lightPathButtons = []

#        # A thread to publish status updates.
#        # This reads temperature updates from the RaspberryPi
#        self.statusThread = threading.Thread(target=self.updateStatus)
#        self.statusThread.Daemon = True
#        self.statusThread.start()
 
        ## Current light path mode.
        self.curExMode = None
        self.curStageMode = None
        self.curDetMode = None


        #Now done via the value logger.
        # ## Matplotlib Figure of temperature data.
        # self.figure = None
        # ## Matplotlib canvas for the plot.
        # self.canvas = None
        # ## History of data we have received. Most recent datapoints are at
        # # the beginning of the array.
        # self.temperatureHistory = numpy.zeros((2, 10))


    ## Connect to the remote program, and set widefield mode.
    def initialize(self):
        self.niConnection = Pyro4.Proxy('PYRO:%s@%s:%d' % ('ni', self.ipAddress, self.port))
        self.temperatureConnection = util.connection.Connection(
                'temperature', self.ipAddress, self.port)
        self.temperatureConnection.connect(self.receiveTemperatureData)
#IMD 20130207 comment out as we are not using it in Oxford
#self.lightConnection = util.connection.Connection(
#                'light', self.ipAddress, self.port)
#        self.lightConnection.connect(self.receiveLightData)
        history = self.niConnection.readTempFile(10)
        if len(history):
            # Strip out the timepoints from the array; we just need the datapoints.
            history = history[:, 1:]
            # We may have fewer than 360 points here, so just copy what we
            # have.
            self.temperatureHistory = history


    ## Try to switch to widefield mode.
    def finalizeInitialization(self):
        self.setExMode(self.excitation[0])
#        self.setStageMode('Inverted')
        #set default emission path
#IMD 20170316 comment out as this is a hack for OMXT
#        self.setDetMode('w/o AO & 209 nm pixel size')
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
        for mode in self.excitation:
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


    #IMD commented out 20170320 as we asre moving all this to config file.
    
#     #IMD 20130227 - added new button stack
#         # stageSizer=wx.BoxSizer(wx.VERTICAL)
#         # label = wx.StaticText(parent, -1, "Stage:")
#         # label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
#         # stageSizer.Add(label)
#         # for mode in ['Inverted', 'Upright']:
#             # button = gui.toggleButton.ToggleButton( 
#                     # textSize = 12, label = mode, size = (180, 50), 
#                     # parent = parent)

#             # wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setStageMode(mode))
#             # stageSizer.Add(button)
#             # self.stagePathButtons.append(button)
#             # if mode == self.curStageMode:
#                 # button.activate()
# #        rowSizer.Add(stageSizer)

# #RK 20130227 - added new button stack
#         detSizer=wx.BoxSizer(wx.VERTICAL)
#         label = wx.StaticText(parent, -1, "Detection path:")
#         label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
#         detSizer.Add(label)
#         for mode in ['with AO & 85 nm pixel size', 'w/o AO & 209 nm pixel size']:
#             button = gui.toggleButton.ToggleButton( 
#                     textSize = 12, label = mode, size = (180, 50), 
#                     parent = parent)

#             wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setDetMode(mode))
#             detSizer.Add(button)
#             self.detPathButtons.append(button)
#             if mode == self.curDetMode:
#                 button.activate()
#         rowSizer.Add(detSizer)


        # #IMX 20170320 commented out as should be moved to valuelogger.
        # plotFrame = wx.Frame(parent, title = "Temperature sensor plot",
        #         style = wx.RESIZE_BORDER | wx.FRAME_TOOL_WINDOW | wx.CAPTION)
        # self.figure = matplotlib.figure.Figure((6, 4), dpi = 100,
        #         facecolor = (1, 1, 1))
        # self.canvas = matplotlib.backends.backend_wxagg.FigureCanvasWxAgg(
        #         plotFrame, -1, self.figure)
        # self.updatePlot()
        # plotFrame.Show()
        # return rowSizer


    ## Set the light path to the specified mode.
    def setExMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.lightPathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curExMode = mode


    def setStageMode(self, mode):
#IMD 20130206 Oxford OMXt doesnt have a diffuser wheel
#        if mode == 'Widefield':
            # Ensure the diffuser wheel is on.
#            handler = depot.getHandlerWithName("Diffuser wheel power")
#            if not handler.getIsOn():
#                wx.MessageDialog(None,
#                        "The diffuser wheel is not active, so Widefield mode " +
#                        "is disabled.",
#                        "Can't use Widefield mode.",
#                        wx.OK | wx.STAY_ON_TOP | wx.ICON_EXCLAMATION
#                ).ShowModal()
#                self.setMode('Structured Illumination')
#                return
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.stagePathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curStageMode = mode

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
        self.niConnection.flipDownUp(index, int(isUp))


    ## Receive temperature data from the remote program's sensors.
    def receiveTemperatureData(self, *args):
        timepoint = args[1]
        values = args[2]
        # Push all existing data over one timepoint and insert the new
        # data at the beginning.
        for i in xrange(len(values)):
                           events.publish("status update",
                           'NIcard',
                           {'temperature'+str(i): values[i],})

    def onObjectiveChange(self, name, pixelSize, transform, offset):
        for flips in self.objectiveToFlips[name]:
            self.flipDownUp(flips[0], flips[1])
        print "NIcard objective change to ",name
#    def onObjectiveChange(self, newName, pixelSize, transform, offset):
#        if (newName=='63x85nm'):
#            self.setDetMode('with AO & 85 nm pixel size')
#        elif (newName=='63x209nm'):
#            self.setDetMode('w/o AO & 209 nm pixel size')

class niOutputWindow(wx.Frame):
    def __init__(self, ni6036e, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## piDevice instance.
        self.nicard = ni6036e
        # Contains all widgets.
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 4, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        # Set up the digital lineout buttons.
        for i in range(len(self.nicard.lines)) :
            button = gui.toggleButton.ToggleButton(
                    parent = panel, label = str(self.nicard.lines[i]),
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
                self.nicard.niConnection.flipDownUp(line, 1)
            else:
                self.nicard.niConnection.flipDownUp(line, 0)




            
## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    niOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
