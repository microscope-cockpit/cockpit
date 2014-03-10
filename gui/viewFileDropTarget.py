import fileViewerWindow

import wx

## Allow users to drag files onto the provided window to pop up a viewer.
class ViewFileDropTarget(wx.FileDropTarget):
    def __init__(self, parent):
        wx.FileDropTarget.__init__(self)
        self.parent = parent


    def OnDropFiles(self, x, y, filenames):
        for filename in filenames:
            window = fileViewerWindow.FileViewer(filename, self.parent)
