import depot
import gui.dialogs.safetyMinDialog
import gui.keyboard
import gui.saveTopBottomPanel
import interfaces.stageMover
import util.userConfig

import macroStageXY
import macroStageZ

import wx


## This class simply contains instances of the various MacroStage
# subclasses, side-by-side, along with the buttons associated
# with each. It also allows for communication between
# the different subclasses, and has some logic that is generally
# related to the UIs the MacroStage instances provide but is not
# tightly bound to any one of them.
class MacroStageWindow(wx.Frame):
    def __init__(self, parent,
                 title = 'Macro Stage XY' + (' ' * 95) +
                 'Macro Stage Z' + (' ' * 10) +
                 'Experiment Histogram',
                 id = -1, pos = (1058, 5),
                 style = wx.CAPTION | wx.FRAME_TOOL_WINDOW):
        wx.Frame.__init__(self, parent, id, title, pos, style = style)

        # For relative sizing of items. The overall window is
        # (width * 10) by (height * 8) pixels. The ratio of
        # these two values is important for proper drawing.
        width = 84
        height = width * 2 / 3.0

        # I apologize for the use of the GridBagSizer here. It's
        # necessary because of the odd shape of the Z macro
        # stage, which is wider than the other elements in its
        # "column".
        # Remember that, in classic "row means X, right?" fashion,
        # WX has flipped its position and size tuples, so 
        # (7, 4) means an X position (or width) of 4, and a Y
        # position/height of 7.
        self.sizer = wx.GridBagSizer()

        self.macroStageXY = macroStageXY.MacroStageXY(self,
                size = (width * 4, height * 7), id = -1)
        self.sizer.Add(self.macroStageXY, (0, 0), (7, 4))
        self.sizer.Add(self.makeXYButtons(), (7, 0), (1, 4))

        self.macroStageZ = macroStageZ.MacroStageZ(self,
                size = (width * 5, height * 6), id = -1)
        self.sizer.Add(self.macroStageZ, (0, 5), (6, 5))

        self.macroStageZKey = macroStageZ.MacroStageZKey(self,
                size = (width * 3, height * 1), id = -1)
        self.sizer.Add(self.macroStageZKey, (6, 5), (1, 3))
        self.sizer.Add(self.makeZButtons(), (7, 5), (1, 3))
        
        ## This allows the user to write notes to themselves, which
        # we save.
        self.comments = wx.TextCtrl(self, -1,
                style = wx.BORDER_SUNKEN | wx.TE_MULTILINE)
        self.comments.SetMinSize((width * 1, height * 6))
        self.comments.Bind(wx.EVT_TEXT, self.onUpdateComments)
        self.sizer.Add(self.comments, (0, 10), (6, 1))
        ## onUpdateComments starts a timer that, when it hits zero,
        # causes us to save the comments. This saves us from
        # writing the config file too often
        self.commentsTimer = wx.Timer(self, -1)
        self.Bind(wx.EVT_TIMER, self.onCommentsTimer, self.commentsTimer)

        self.saveTopBottomPanel = gui.saveTopBottomPanel.createSaveTopBottomPanel(self)
        self.sizer.Add(self.saveTopBottomPanel, (6, 8), (2, 3))
        
        self.SetSizerAndFit(self.sizer)
        self.SetBackgroundColour((255, 255, 255))
        self.Layout()
        self.Show(True)

        gui.keyboard.setKeyboardHandlers(self)


    ## Returns a sizer containing a set of buttons related to the XY macro stage
    def makeXYButtons(self):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        button = wx.Button(self, -1, "Set safeties")
        button.SetToolTip(wx.ToolTip("Click twice on the XY Macro Stage view " +
                "to set the XY motion limits."))
        button.Bind(wx.EVT_BUTTON, self.macroStageXY.setSafeties)
        sizer.Add(button)
        
        self.motionControllerButton = wx.Button(self, -1, "Switch control")
        self.motionControllerButton.SetToolTip(wx.ToolTip(
                "Change which stage motion device the keypad controls."))
        self.motionControllerButton.Bind(wx.EVT_BUTTON, 
                lambda event: interfaces.stageMover.changeMover())
        sizer.Add(self.motionControllerButton)

        button = wx.Button(self, -1, "Recenter")
        button.Bind(wx.EVT_BUTTON, 
                lambda event: interfaces.stageMover.recenterFineMotion())
        sizer.Add(button)
        return sizer

    ## Returns a sizer containing a set of buttons related to the Z macro stage
    def makeZButtons(self):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        button = wx.Button(self, -1, "Set safeties")
        button.Bind(wx.EVT_BUTTON, 
                lambda event: gui.dialogs.safetyMinDialog.showDialog(self.GetParent()))
        sizer.Add(button)
        
        button = wx.Button(self, -1, "Touch down")
        touchdownAltitude = depot.getHandlersOfType(depot.CONFIGURATOR)[0].getValue('slideTouchdownAltitude')
        button.SetToolTip(wx.ToolTip(u"Bring the stage down to %d\u03bcm" % touchdownAltitude))
        button.Bind(wx.EVT_BUTTON, 
                lambda event: interfaces.stageMover.goToZ(touchdownAltitude))
        sizer.Add(button)

        return sizer


    ## The user updated the comments. Start a countdown to
    # save the contents when they stop typing.
    def onUpdateComments(self, event):
        self.commentsTimer.Stop()
        self.commentsTimer.Start(10000)


    ## Save the contents of the comments box.
    def onCommentsTimer(self, event):
        content = self.comments.GetValue()
        util.userConfig.setValue('histogramComments', content)
        self.commentsTimer.Stop()


    ## Passthrough to MacroStageXY.setXYLimit()
    def setXYLimit(self, *args):
        self.macroStageXY.setXYLimit(*args)



window = None
## Create the MacroStageWindow singleton
def makeWindow(parent):
    global window
    window = MacroStageWindow(parent)
    window.SetPosition((1280, 0))

# Below this point are functions for exposing parts of the
# MacroStageWindow singleton

## Passthrough
def setXYLimit():
    window.setXYLimit()


## Signals that the user has logged in and we can grab
# any config-dependent values.
def userLoggedIn():
    comments = util.userConfig.getValue('histogramComments', default = '')
    window.comments.SetValue(comments)
