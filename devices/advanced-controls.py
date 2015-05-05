# module to provide buttons to link to the advaced controls of various
# pieces of hardware eg dsp, DIO, etc....
# IMD 20150505
#

import wx
import devices.dsp as DSP
import devices.pi-DIO as DIO

from config import config
CLASS_NAME = 'AdvancedControl'
CONFIG_NAME = 'advCtl'



class advancedControl(devices.Device):
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
        label = wx.StaticText(panel, -1, "Advanced Controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        panelSizer.Add(label)
        
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        button = gui.toggleButton.ToggleButton(
                label = "DSP\nTTL", parent = panel, size = (84, 50))
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: DSP.makeOutputWindow())
        buttonSizer.Add(button)

        button = gui.toggleButton.ToggleButton(
                label = "pi-DIO", parent = panel, size = (84, 50))
        button.Bind(wx.EVT_LEFT_DOWN, lambda event: DIO.makeOutputWindow())
        buttonSizer.Add(button)

        panelSizer.Add(buttonSizer)
        panel.SetSizerAndFit(panelSizer)
        
        return panel
