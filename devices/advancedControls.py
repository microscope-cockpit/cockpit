# module to provide buttons to link to the advaced controls of various
# pieces of hardware eg dsp, DIO, etc....
# IMD 20150505
#

import wx
import device
import devices.dsp as DSP
import devices.piDIO as DIO
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
        for dev in devs :
            if hasattr(dev,'makeOutputWindow'):
                if callable(dev,'makeOutputWindow'):
                    button = gui.toggleButton.ToggleButton(
                          label = dev.__class__.__name__, parent = panel, size = (84, 50))
                    button.Bind(wx.EVT_LEFT_DOWN, lambda event: dev.makeOutputWindow())
                    buttonSizer.Add(button)
 
 
     #   panelSizer.Add(buttonSizer)
      #  panel.SetSizerAndFit(panelSizer)
        
        return panel
