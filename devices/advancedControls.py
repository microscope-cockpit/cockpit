# module to provide buttons to link to the advaced controls of various
# pieces of hardware eg dsp, DIO, etc....
# IMD 20150505
#
# Requires some setup in the device file.
# 1) device must have a callable makeOutputWindow function
# 2) This function must be accessible as self.makeOutputWindow from within the device context
# and the function must create a window with the relevant controls in it.
# 3) Device file must also have self.buttonName variable as a string which the advanced 
#	controls button will be labelled with.
# See either dsp.py or piDIO.py for examples. 
# These examples are slightly more complex as they have makeOutputWindow also accessible from
# ouside the device context to allow easy access to them from the python command line via
# import devices.dsp as DSP
# DSP.makeOutputWindow()
#
# If the config has an [advCtl] section then this feature will be activated otherwise it does nothing.
#

import wx
import device
import gui.toggleButton
import depot

from config import config
CLASS_NAME = 'AdvancedControl'
CONFIG_NAME = 'advCtl'



class AdvancedControl(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 10000
        if not self.isActive:
            return

    def initialize(self):
        pass

    def makeInitialPublications(self):
        pass

    def makeUI(self, parent):
        panel = wx.Panel(parent)
        panelSizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, -1, "Advanced\nControls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        panelSizer.Add(label)
        devs = depot.getAllDevices()
        buttonSizer = wx.BoxSizer(wx.VERTICAL)
        advancedDevList=[]
        i=0
        for dev in devs :
            if hasattr(dev,'makeOutputWindow'):
                if callable(dev.makeOutputWindow):
                    advancedDevList.append (dev.makeOutputWindow)
                    button = gui.toggleButton.ToggleButton(
                          label = dev.buttonName, parent = panel, size = (84, 50))
						  
                    button.Bind(wx.EVT_LEFT_DOWN, dev.makeOutputWindow)#lambda event: advancedDevList[i])
                    buttonSizer.Add(button)
                    i=i+1
 
 
        panelSizer.Add(buttonSizer)
        panel.SetSizerAndFit(panelSizer)
        
        return panel
