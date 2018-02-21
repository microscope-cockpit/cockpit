import threading
import time
import wx


## @package gui.guiUtils
# This module contains many functions related to the GUI, mostly for setting
# up UI elements and updating various status displays.


## Create a basic panel with some text.
def createTextPanel(parent, panelId, textId, textContent, panelStyle = 0, 
                    textStyle = 0, isBold = True,
                    orientation = wx.HORIZONTAL,
                    minSize = None):
    panel = wx.Panel(parent, panelId, style = panelStyle)
    text = wx.StaticText(panel, textId, textContent, style = textStyle)
    fontStyle = wx.BOLD
    if not isBold:
        fontStyle = wx.NORMAL
    text.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, fontStyle))
    sizer = wx.BoxSizer(orientation)
    sizer.Add(text, 1)
    if minSize is not None:
        sizer.SetMinSize(minSize)
    panel.SetSizerAndFit(sizer)
    panel.Show(0)
    return (panel, text)


## Width of a normal button (as opposed to a custom UI element, like
# a ToggleButton).
ORDINARY_BUTTON_WIDTH = 100
## Create a header string in a large font, along with a help
# button and any other provided buttons
def makeHeader(parent, label, helpString = '',
               extraButtons = [], buttonSize = (ORDINARY_BUTTON_WIDTH, -1)):
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    text = wx.StaticText(parent, -1, label)
    text.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
    sizer.Add(text)
    if helpString:
        button = wx.Button(parent, -1, "Help",
                size = (ORDINARY_BUTTON_WIDTH, -1))
        button.Bind(wx.EVT_BUTTON, lambda event: showHelpDialog(parent, helpString))
        sizer.Add(button, 0, wx.LEFT, 10)
    for button in extraButtons:
        button.SetSize(buttonSize)
        sizer.Add(button)
    return sizer


## Generate a set of small text boxes for controlling individual lights.
# Return a list of the controls, and the sizer they are contained in.
def makeLightsControls(parent, labels, defaults):
    sizer = wx.FlexGridSizer(2, len(labels), 0)
    for label in labels:
        sizer.Add(wx.StaticText(parent, -1, label),
                0, wx.ALIGN_RIGHT | wx.ALL, 5)
    controls = []
    for defaultVal in defaults:
        control = wx.TextCtrl(parent, size = (40, -1))
        control.SetValue(defaultVal)
        controls.append(control)
        sizer.Add(control, 0, wx.ALL, 5)
    return controls, sizer



## Show an informative dialog
def showHelpDialog(parent, text):
    wx.MessageDialog(parent, text,
            style = wx.ICON_INFORMATION | wx.OK).ShowModal()


## Add some explanatory text to the given sizer.
def addHelperString(parent, sizer, text, border = 0, flags = wx.ALL):
    label = wx.StaticText(parent, -1, " (What is this?)")
    label.SetForegroundColour((100, 100, 255))
    label.SetToolTip(wx.ToolTip(text))
    sizer.Add(label, 0, flags, border)


## Add a labeled form input to the given sizer. Note that if you pass in
# a wx.CheckBox input, then the input and the explanatory text are swapped.
# @param defaultValue The default value the form input should have.
# @param labelHeightAdjustment Number of pixels to push the input's label down
# by. Sometimes labels and inputs don't align nicely otherwise.
# @param controlType The type of the form input to make. Defaults to 
#        wx.TextCtrl.
# @param control The specific control object to use. Mutually exclusive
#        with the controlType parameter.
# @param helperString Help text to insert, using addHelperString.
# @param flags Any wx flags to use when inserting the object into the sizer.
# \todo The checkbox logic results in substantial code duplication.
def addLabeledInput(parent, sizer, id = -1, label = '',
                    defaultValue = '', size = (-1, -1), minSize = (-1, -1),
                    shouldRightAlignInput = True, border = 0, labelHeightAdjustment = 3,
                    control = None, controlType = None, helperString = '',
                    flags = wx.ALL):
    if control is None:
        if controlType is None:
            controlType = wx.TextCtrl
        control = controlType(parent, id, defaultValue, size = size)
    text = wx.StaticText(parent, -1, label)
    rowSizer = wx.BoxSizer(wx.HORIZONTAL)
    rowSizer.SetMinSize(minSize)

    if controlType == wx.CheckBox:
        rowSizer.Add(control)
        if shouldRightAlignInput:
            rowSizer.Add((10, -1), 1, wx.EXPAND | wx.ALL, 0)
        rowSizer.Add(text, 0, wx.TOP, labelHeightAdjustment)
        if helperString != '':
            addHelperString(parent, rowSizer, helperString,
                    border = labelHeightAdjustment, flags = wx.TOP)
    else:
        rowSizer.Add(text, 0, wx.TOP, labelHeightAdjustment)
        if helperString != '':
            addHelperString(parent, rowSizer, helperString,
                    border = labelHeightAdjustment, flags = wx.TOP)
        if shouldRightAlignInput:
            # Add an empty to suck up horizontal space
            rowSizer.Add((10, -1), 1, wx.EXPAND | wx.ALL, 0)
        rowSizer.Add(control)
    sizer.Add(rowSizer, 1, flags | wx.EXPAND, border)
    return control


## Simple utility function to pop up the supplied menu at the current 
# mouse location.
def placeMenuAtMouse(frame, menu):
    # Get the Mouse Position on the Screen 
    mousePos = wx.GetMousePosition()
    # Translate the Mouse's Screen Position to the Mouse's Control Position 
    mousePosRelative = frame.ScreenToClient(mousePos)
    frame.PopupMenu(menu, mousePosRelative)


## Pop up a warning dialog, and return the user's reaction.
def getUserPermission(text, title = 'Warning'):
    response = wx.MessageDialog(None, text, title, 
            wx.CANCEL | wx.OK | wx.STAY_ON_TOP | wx.ICON_EXCLAMATION).ShowModal()
    return response == wx.ID_OK


## Given a control, try to parse its value as a number, returning a
# default value on failure.
def tryParseNum(control, convertFunc = int, default = 0):
    try:
        return convertFunc(control.GetValue())
    except:
        return default



## This class waits a specified amount of time and then displays a message
# dialog unless told to stop.
class WaitMessageDialog(threading.Thread):
    def __init__(self, message, title, waitTime):
        threading.Thread.__init__(self)
        self.message = message
        self.title = title
        self.waitTime = waitTime
        ## Set to True to stop showing the dialog, or never show it if it
        # hasn't been shown yet.
        self.shouldStop = False


    def run(self):
        time.sleep(self.waitTime)
        if not self.shouldStop:
            dialog = wx.ProgressDialog(parent = None,
                    title = self.title, message = self.message)
            dialog.Show()
            while not self.shouldStop:
                time.sleep(.01)
            dialog.Hide()
            dialog.Destroy()
