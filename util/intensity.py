#!/usr/bin/python
# -*- coding: UTF8   -*-
import matplotlib.pyplot as plt
import Mrc
import numpy as np
import sys
import wx
from wx.lib.floatcanvas import FloatCanvas

ICON_SIZE = (16,16)
BITMAP_SIZE = (512,512)

class IntensityProfiler(object):
    def __init__(self):
        self._data = None
        self._projection = None
        self.centre = None


    def setData(self, data):
        self._data = data
        self._projection = None


    def guessBeadCentre(self):
        if self._data is None:
            return
        nz, ny, nx  = self._data.shape
        middle = self._data[:,
                           3*ny / 8 : 5*ny / 8,
                           3*nx / 8 : 5*nx / 8]
        slicesize = middle.shape[-1] * middle.shape[-2]
        peakPosition = np.argmax(middle)
        (z, y, x) = np.unravel_index(peakPosition, middle.shape)
        xOffset = nx/2 - middle.shape[-1]/2
        yOffset = ny/2 - middle.shape[-2]/2
        self.centre = (x + xOffset, y + yOffset)
        return self.centre


    def getProjection(self):
        if self._projection is None:
            nz = self._data.shape[0]
            dz = min(30, nz / 8)
            self._projection = np.mean(self._data[nz/2 - dz : nz/2 + dz, :, :],
                                      axis=0)
        return self._projection.copy()


class IntensityProfilerFrame(wx.Frame):
    def __init__(self, parent=None):
        super(IntensityProfilerFrame, self).__init__(parent, title="SIM intensity profile")
        self.profiler = IntensityProfiler()
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar = wx.ToolBar(self, -1)
        openTool = toolbar.AddSimpleTool(
                        wx.ID_ANY,
                        wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, ICON_SIZE),
                        "Open", "Open a dataset")
        toolbar.AddSeparator()
        goTool = toolbar.AddSimpleTool(
                        wx.ID_ANY,
                        wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR, ICON_SIZE),
                        "Go", "Evaluate intensity profile")
        toolbar.Realize()
        vbox.Add(toolbar, 0, border=5)        
        self.Bind(wx.EVT_TOOL, self.loadFile, openTool)
        
        # Canvas
        self.canvas = FloatCanvas.FloatCanvas(self, size=(512,512))
        img = wx.EmptyImage(BITMAP_SIZE[0], BITMAP_SIZE[1], False)
        self.bitmap = self.canvas.AddBitmap(img, (0,0), 'cc', False)
        self.circle = self.canvas.AddCircle((0,0), 10, '#ff0000')

        self.canvas.Draw()
        vbox.Add(self.canvas)
        


        self.SetSizerAndFit(vbox)


    def loadFile(self, event):
        top = wx.GetApp().TopWindow
        dlg = wx.FileDialog(top, "Open", "", "", "",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        else:
            return
        data = Mrc.bindFile(filename)
        self.profiler.setData(data)

        # Guess a bead position      
        xpos, ypos = self.profiler.guessBeadCentre()
        self.circle.SetPoint(self.canvas.PixelToWorld((xpos, ypos)))

        # Update the bitmap
        proj = self.profiler.getProjection()
        proj -= np.min(proj)
        proj /= np.max(proj)
        proj = (proj * 255).astype(np.uint8)
        d = range(-10,-3) + range(3, 10)
        img = np.dstack((proj, proj, proj))
        nx, ny = proj.shape
        self.bitmap.Bitmap.SetSize((nx,ny))
        self.bitmap.Bitmap.CopyFromBuffer(img.tostring())

        self.canvas.Draw(Force=True)


def main():
    import wx.lib.inspection
    app = wx.App(False)
    ip = IntensityProfilerFrame()
    ip.Show()
    wx.lib.inspection.InspectionTool().Show()
    app.MainLoop()

if __name__ == '__main__':
    main()