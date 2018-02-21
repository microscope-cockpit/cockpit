import wx
import experimentConfigPanel

## A simple wrapper around the ExperimentConfigPanel class.
class SingleSiteExperimentDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent,
                title = "OMX single-site experiment",
                style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        ## Contains all the actual UI elements beyond the dialog window itself.
        self.panel = experimentConfigPanel.ExperimentConfigPanel(self,
                resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onReset)
        self.sizer.Add(self.panel)
        
        self.buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        button = wx.Button(self, -1, "Reset")
        button.SetToolTip(wx.ToolTip("Reload this window with all default values"))
        button.Bind(wx.EVT_BUTTON, self.onReset)
        self.buttonBox.Add(button, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.buttonBox.Add((1, 1), 1, wx.EXPAND)

        button = wx.Button(self, wx.ID_CANCEL, "Cancel")
        self.buttonBox.Add(button, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        
        button = wx.Button(self, wx.ID_OK, "Start")
        button.SetToolTip(wx.ToolTip("Start the experiment"))
        button.Bind(wx.EVT_BUTTON, self.onStart)
        self.buttonBox.Add(button, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.sizer.Add(self.buttonBox, 1, wx.EXPAND)
        
        self.SetSizerAndFit(self.sizer)


    ## Our experiment panel resized itself.
    def onExperimentPanelResize(self, panel):
        self.SetSizerAndFit(self.sizer)
    

    ## Attempt to run the experiment. If the testrun fails, report why.
    def onStart(self, event = None):
        message = self.panel.runExperiment()
        if message is not None:
            wx.MessageBox("The experiment cannot be run:\n%s" % message,
                    "Error", wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
            return
        else:
            self.Hide()


    ## Blow away the experiment panel and recreate it from scratch.
    def onReset(self, event = None):
        self.sizer.Remove(self.panel)
        self.panel.Destroy()
        self.panel = experimentConfigPanel.ExperimentConfigPanel(self,
                resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onReset)
        self.sizer.Prepend(self.panel)
        self.sizer.Layout()
        self.Refresh()
        self.SetSizerAndFit(self.sizer)
        return self.panel
        
        


## Global singleton
dialog = None


def showDialog(parent):
    global dialog
    if not dialog:
        dialog = SingleSiteExperimentDialog(parent)
    dialog.Show()
