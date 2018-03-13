import depot
import gui.guiUtils
import interfaces.stageMover
import util.userConfig

import wx
import numpy


## This class shows a simple dialog to the user that allows them to lay down
# a grid of sites on the mosaic. They can then use this to image large areas
# in a regulated manner without relying on the mosaic's spiral system. 
class GridSitesDialog(wx.Dialog):
    ## Create the dialog, and lay out its UI widgets. 
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, "Place a Grid of Sites")

        ## Config-loaded settings for the form.
        self.settings = util.userConfig.getValue('gridSitesDialog', default = {
                'numRows' : '10',
                'numColumns' : '10',
                'imageWidth' : '512',
                'imageHeight' : '512',
                'markerSize': '25',
            }
        )
        
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1,
                "The upper-left corner of the grid will be at the current " +
                "stage position.")
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        self.numRows = gui.guiUtils.addLabeledInput(self, sizer,
                label = "Number of rows:",
                defaultValue = self.settings['numRows'])
        self.numColumns = gui.guiUtils.addLabeledInput(self, sizer,
                label = "Number of columns:",
                defaultValue = self.settings['numColumns'])
        self.imageWidth = gui.guiUtils.addLabeledInput(self, sizer,
                label = "Horizontal spacing (pixels):",
                defaultValue = self.settings['imageWidth'])
        self.imageHeight = gui.guiUtils.addLabeledInput(self, sizer,
                label = "Vertical spacing (pixels):",
                defaultValue = self.settings['imageHeight'])
        self.markerSize = gui.guiUtils.addLabeledInput(self, sizer,
                label = "Marker size (default 25):",
                defaultValue = self.settings['markerSize'])
        
        buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        cancelButton = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancelButton.SetToolTipString("Close this window")
        buttonBox.Add(cancelButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        
        startButton = wx.Button(self, wx.ID_OK, "Mark sites")
        buttonBox.Add(startButton, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        buttonBox.Add((20, -1), 1, wx.ALL, 5)
        sizer.Add(buttonBox, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.Bind(wx.EVT_BUTTON, wx.ID_OK, self.OnStart)


    ## Create the grid of sites. 
    def OnStart(self, evt):
        self.saveSettings()

        curLoc = interfaces.stageMover.getPosition()
        imageWidth = float(self.imageWidth.GetValue())
        imageHeight = float(self.imageHeight.GetValue())
        markerSize = float(self.markerSize.GetValue())
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        pixelSize = objective.getPixelSize()

        for xOffset in range(int(self.numColumns.GetValue())):
            xLoc = curLoc[0] - xOffset * pixelSize * imageWidth
            for yOffset in range(int(self.numRows.GetValue())):
                yLoc = curLoc[1] - yOffset * pixelSize * imageHeight
                target = numpy.array([xLoc, yLoc, curLoc[2]])
                newSite = interfaces.stageMover.Site(target, size = markerSize)
                interfaces.stageMover.saveSite(newSite)
        self.Destroy()


    ## Save the user's settings to the configuration file.
    def saveSettings(self):
        util.userConfig.setValue('gridSitesDialog', {
                'numRows': self.numRows.GetValue(),
                'numColumns': self.numColumns.GetValue(),
                'imageWidth': self.imageWidth.GetValue(),
                'imageHeight': self.imageHeight.GetValue(),
                'markerSize': self.markerSize.GetValue(),
            }
        )
        

## Show the dialog.
def showDialog(parent):
    dialog = GridSitesDialog(parent)
    dialog.Show()
    dialog.SetFocus()
    return dialog
