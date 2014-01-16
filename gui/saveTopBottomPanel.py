import interfaces.stageMover

import wx

## @package saveTopBottomPanel
# This module handles code related to the UI widget for saving the current
# stage altitude as a "top" or "bottom".
# \todo This should be a proper singleton class instead of a bunch of functions
# and module-level variables.

## Text control for the altitude at the "top"
topPosControl = None
## Text control for the altitude at the "bottom"
bottomPosControl = None
## Text label for the total height of the stack. 
zStackHeightLabel = None

## Current saved top position
savedTop = 7780
## Current saved bottom position
savedBottom = 7770


## Create and lay out the "save top/bottom" panel, which allows the user to 
# remember Z levels of interest.
def createSaveTopBottomPanel(parent):
    global topPosControl, zStackHeightLabel, bottomPosControl
    panel = wx.Panel(parent, 8910)

    box = wx.StaticBox(panel, -1, '')
    
    sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
    panel.SetSizer(sizer)

    box = wx.FlexGridSizer(3, 3, 0, 0)
    sizer.Add(box, 0, wx.ALIGN_CENTER | wx.ALL, 1)

    saveTop = wx.Button(panel, 8911 , "Save top", size=(75, -1))
    box.Add(saveTop, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    topPosControl = wx.TextCtrl(panel, 8913, '0', style = wx.TE_RIGHT,size = (60, -1))
    box.Add(topPosControl, 1, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoTop = wx.Button(panel, 8915, "Go to top", size = (75, -1))
    box.Add(gotoTop, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    label = wx.StaticText(panel, -1, u"z-height (\u03bcm):")
    box.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

    zStackHeightLabel = wx.StaticText(panel, -1, '0', 
            style = wx.TE_RIGHT, size = (60, -1))
    box.Add(zStackHeightLabel, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoCenter = wx.Button(panel, 8917, "Go to center", size = (75, -1))
    box.Add(gotoCenter, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    saveBot = wx.Button(panel, 8912, "Save bottom", size = (75, -1))
    box.Add(saveBot, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    bottomPosControl  = wx.TextCtrl(panel, 8914, '0', 
            style = wx.TE_RIGHT, size = (60, -1))
    box.Add(bottomPosControl, 1, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoBottom = wx.Button(panel, 8916, "Go to bottom", size = (75, -1))
    box.Add(gotoBottom, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    topPosControl.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    bottomPosControl.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    zStackHeightLabel.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    
    panel.SetAutoLayout(1)
    sizer.Fit(panel)

    topPosControl.SetValue("%.1f" % savedTop)
    bottomPosControl.SetValue("%.1f" % savedBottom)
    updateZStackHeight()
    
    wx.EVT_BUTTON(parent, 8911, OnTB_saveTop)
    wx.EVT_BUTTON(parent, 8912, OnTB_saveBottom)
    wx.EVT_BUTTON(parent, 8915, OnTB_gotoTop)
    wx.EVT_BUTTON(parent, 8916, OnTB_gotoBottom)
    wx.EVT_TEXT(parent, 8913, OnTB_TextEdit)
    wx.EVT_TEXT(parent, 8914, OnTB_TextEdit)

    wx.EVT_BUTTON(parent, 8917, OnTB_gotoCenter)
    return panel
    

## Event for handling users clicking on the "save top" button. Set savedTop.
def OnTB_saveTop(ev):
    global savedTop
    savedTop = interfaces.stageMover.getPosition()[2]
    topPosControl.SetValue("%.1f" % savedTop)
    updateZStackHeight()


## Event for handling users clicking on the "save bottom" button. Set 
# savedBottom.
def OnTB_saveBottom(ev):
    global savedBottom
    savedBottom = interfaces.stageMover.getPosition()[2]
    bottomPosControl.SetValue("%.1f" % savedBottom)
    updateZStackHeight()


## Event for handling users clicking on the "go to top" button. Use the 
# nanomover (and, optionally, also the stage piezo) to move to the target
# elevation.
def OnTB_gotoTop(ev):
    interfaces.stageMover.goToZ(savedTop)


## As OnTB_gotoTop, but for the bottom button instead.
def OnTB_gotoBottom(ev):
    interfaces.stageMover.goToZ(savedBottom)

## As OnTB_gotoTop, but for the middle button instead. 
def OnTB_gotoCenter(ev):
    target = savedBottom + ((savedTop - savedBottom) / 2.0)
    interfaces.stageMover.goToZ(target)


## Event for when users type into one of the text boxes for the save top/bottom
# controls. Automatically update the saved top and bottom values.
def OnTB_TextEdit(ev):
    global savedTop, savedBottom
    savedBottom = float(bottomPosControl.GetValue())
    savedTop = float(topPosControl.GetValue())
    updateZStackHeight()


## Whenever the saved top/bottom are changed, this is called to update the 
# displayed distance between the two values.
def updateZStackHeight():
    zStackHeightLabel.SetLabel("%.2f" % (savedTop - savedBottom))


## Get the bottom and top of the stack.
def getBottomAndTop():
    return (savedBottom, savedTop)
