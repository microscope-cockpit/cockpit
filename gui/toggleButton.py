import wx

## @package gui.toggleButton
# This module contains the ToggleButton class and all functions
# associated with that class.

## Color for active controls, barring control-specific colors
ACTIVE_COLOR = (128, 255, 125)
## Color for inactive controls, barring control-specific colors
INACTIVE_COLOR = (128, 128, 128)
## Default size
DEFAULT_SIZE=(128, 48)


## This class provides a simple button that can be toggled on and off, and
# allows you to specify functions to call when it is activated/deactivated.
# It's up to you to handle binding click events and actually
# activating/deactivating it, though.
class ToggleButton(wx.StaticText):
    ## Instantiate the button.
    # \param activeColor Background color when activate() is called
    # \param activeLabel Optional label to switch to when activate() is called
    # \param activateAction Function to call when activate() is called
    # \param inactiveColor As activeColor, but for deactivate()
    # \param inactiveLabel As activeLabel, but for deactivate()
    # \param deactivateAction As activateAction, but for deactivate()
    # \param tooltip Tooltip string to display when moused over
    def __init__(self, 
                 activeColor = ACTIVE_COLOR, inactiveColor = INACTIVE_COLOR, 
                 activateAction = None, deactivateAction = None,
                 activeLabel = None, inactiveLabel = None,
                 tooltip = '', textSize = 12, isBold = True, **kwargs):
        # Default size:
        if 'size' not in kwargs:
            kwargs['size'] = DEFAULT_SIZE
        wx.StaticText.__init__(self,
                style = wx.RAISED_BORDER | wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE,
                **kwargs)
        flag = wx.FONTWEIGHT_BOLD
        if not isBold:
            flag = wx.FONTWEIGHT_NORMAL
        self.SetFont(wx.Font(textSize,wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, flag))
        self.SetToolTip(wx.ToolTip(tooltip))
        self.activeColor = activeColor
        self.inactiveColor = inactiveColor
        self.baseLabel = self.GetLabel()
        self.activeLabel = activeLabel
        self.inactiveLabel = inactiveLabel
        self.activateAction = activateAction
        self.deactivateAction = deactivateAction
        self.SetBackgroundColour(self.inactiveColor)
        self.isActive = False
        # Realign the label using our custom version of the function
        self.SetLabel(self.GetLabel())
        self.Bind(wx.EVT_LEFT_DOWN, lambda event: self.toggle())
        #self.Bind(wx.EVT_RIGHT_DOWN, lambda event: self.toggle())


    ## Override of normal StaticText SetLabel, to try to vertically
    # align the text.
    def SetLabel(self, text, *args, **kwargs):
        height = self.GetSize()[1]
        font = self.GetFont()
        fontHeight = font.GetPointSize()
        maxLines = min(height / fontHeight, max)
        numLinesUsed = len(text.split("\n"))
        lineBuffer = (maxLines - numLinesUsed) / 2 - 1
        newText = ("\n" * lineBuffer) + text + ("\n" * lineBuffer)
        wx.StaticText.SetLabel(self, newText, *args, **kwargs)


    ## Update the button to match known state.
    def updateState(self, isActive):
        if isActive == self.isActive:
            # Do nothing if state is correct.
            return
        if isActive:
            color = self.activeColor
            label = self.activeLabel or self.baseLabel
        else:
            color = self.inactiveColor
            label = self.inactiveLabel or self.baseLabel
        self.SetBackgroundColour(color)
        self.SetLabel(label)
        self.Refresh()


    ## Activate or deactivate based on the passed-in boolean
    def setActive(self, shouldActivate, extraText = ''):
        if shouldActivate:
            self.activate(extraText)
        else:
            self.deactivate(extraText)
            

    def activate(self, extraText = ''):
        result = None
        self.isActive = True
        if self.activateAction is not None:
            result = self.activateAction()
        self.SetBackgroundColour(self.activeColor)
        
        label = self.baseLabel
        if self.activeLabel is not None:
            label = self.activeLabel
        if extraText:
            label += '\n' + extraText
        self.SetLabel(label)
        
        self.Refresh()
        return result


    def deactivate(self, extraText = ''):
        result = None
        self.isActive = False
        if self.deactivateAction is not None:
            result = self.deactivateAction()
        self.SetBackgroundColour(self.inactiveColor)
        
        label = self.baseLabel
        if self.inactiveLabel is not None:
            label = self.inactiveLabel
        if extraText:
            label += '\n' + extraText
        self.SetLabel(label)

        self.Refresh()
        return result


    def getIsActive(self):
        return self.isActive


    def toggle(self):
        self.setActive(not self.isActive)


## Enable the specified control, and disable all controls in the given list
# that are not that control.
def activateOneControl(control, listOfControls):
    control.activate()
    for altControl in listOfControls:
        if altControl != control:
            altControl.deactivate()
