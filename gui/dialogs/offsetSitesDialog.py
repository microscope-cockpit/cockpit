import gui.guiUtils

import wx

## @package dialogs.offsetSitesDialog
# This module contains the \link dialogs.offsetSitesDialog.OffsetSites_Dialog
# OffsetSites_Dialog \endlink
# class, and code for displaying it.

## This dialog allows the user to add a positional offset to a selection
# of sites.
class OffsetSites_Dialog(wx.Dialog):
    ## Create the dialog, and lay out its UI widgets. 
    def __init__(self, parent, *args):
        wx.Dialog.__init__(self, parent, -1, "Move Sites", *args)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, -1, "What offset should we apply?")
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        self.controls = []
        for label in ('X', 'Y', 'Z'):
            self.controls.append(gui.guiUtils.addLabeledInput(
                    parent = self, sizer = sizer,
                    label = "%s:" % label, defaultValue = '',
                    size = (60, -1), minSize = (100, -1),
                    border = 5,
                    flags = wx.ALIGN_CENTRE | wx.ALL)
            )
        
        buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancelButton.SetToolTip(wx.ToolTip("Close this window"))
        buttonBox.Add(cancelButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Move sites")
        buttonBox.Add(startButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        buttonBox.Add((20, -1), 1, wx.ALL, 5)
        sizer.Add(buttonBox, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)


    ## Return a list of floats indicating the offset to add.
    def getOffset(self):
        result = []
        for control in self.controls:
            if control.GetValue():
                result.append(float(control.GetValue()))
            else:
                result.append(0)
        return result



## Show the dialog. If it has not been created yet, then create it first.
def showDialogModal(parent):
    dialog = OffsetSites_Dialog(parent)
    if dialog.ShowModal() == wx.ID_OK:
        return dialog.getOffset()
    return None
