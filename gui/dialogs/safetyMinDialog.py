import gui.guiUtils
import interfaces.stageMover

import wx

## @package safetyMinDialog.py
# This package contains the SafetyMin_Dialog class and associated constants and
# functions.

## Altitude for slides.
SLIDE_SAFETY = 7300
## Altitude for dishes.
DISH_SAFETY = 5725


## This class provides a simple wrapper around the interfaces.stageMover's
# safety functionality.
# Note that unlike most
# dialogs, this one does not save the user's settings; instead, it always
# shows the current safety min as the default setting. This is to keep
# users from blindly setting the safety min to what they always use;
# we want them to think about what they're doing.
class SafetyMinDialog(wx.Dialog):
    def __init__(
            self, parent, size = wx.DefaultSize, pos = wx.DefaultPosition, 
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.TAB_TRAVERSAL
            ):
        wx.Dialog.__init__(self, parent, -1, "Set Z motion minimum", 
                pos, size, style)
        
        self.mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.mainSizer.Add(wx.StaticText(self, -1, 
                "Set the minimum altitude the stage is allowed\n" + 
                "to move to."),
                0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)

        self.minStageZ = gui.guiUtils.addLabeledInput(
                parent = self, sizer = self.mainSizer,
                label = u"Stage Z minimum (\u03bcm):",
                defaultValue = str(interfaces.stageMover.getSoftLimits()[2][0]),
                size = (70, -1), minSize = (150, -1), 
                shouldRightAlignInput = True, border = 3, 
                controlType = wx.TextCtrl)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        slideSafetyButton = wx.Button(self, -1, "Slide")
        slideSafetyButton.SetToolTip(wx.ToolTip("Set the safety to a good value for slide experiments"))
        slideSafetyButton.Bind(wx.EVT_BUTTON, lambda event: self.setSafetyText(SLIDE_SAFETY))
        rowSizer.Add(slideSafetyButton, 0, wx.ALL, 5 )
        dishSafetyButton = wx.Button(self, -1, "Dish")
        dishSafetyButton.SetToolTip(wx.ToolTip("Set the safety to a good value for dish experiments"))
        dishSafetyButton.Bind(wx.EVT_BUTTON, lambda event: self.setSafetyText(DISH_SAFETY))
        rowSizer.Add(dishSafetyButton, 0, wx.ALL, 5)

        self.mainSizer.Add(rowSizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        buttonsBox = wx.BoxSizer(wx.HORIZONTAL)

        cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        buttonsBox.Add(cancelButton, 0, wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Apply")
        startButton.SetToolTip(wx.ToolTip("Apply the chosen safety min"))
        buttonsBox.Add(startButton, 0, wx.ALL, 5)
        
        self.mainSizer.Add(buttonsBox, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 3)

        self.SetSizer(self.mainSizer)
        self.SetAutoLayout(True)
        self.mainSizer.Fit(self)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnStart)


    ## Set the text for the stage safety min to a default value.
    def setSafetyText(self, value):
        self.minStageZ.SetValue('%.1f' % value)
    

    ## Save the user's selected Z min to the user config, and then set the 
    # new min.
    def OnStart(self, event):
        self.Hide()
        interfaces.stageMover.setSoftMin(2, float(self.minStageZ.GetValue()))


## Global dialog singleton.
dialog = None

## Generate the dialog for display. If it already exists, just bring it
# forwards.
def showDialog(parent):
    global dialog
    if dialog:
        try:
            dialog.Show()
            dialog.SetFocus()
            return
        except:
            # dialog got destroyed, so just remake it.
            pass
    dialog = SafetyMinDialog(parent)
    dialog.Show()


