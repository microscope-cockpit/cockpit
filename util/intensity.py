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
        self._beadCntre = None
        self._phases = 5


    def calculateInstensity(self):
        if self._data is None:
            return
        if self._beadCentre is None:
            self.guessBeadCentre()
        # Estimate background from image corners.
        nz, ny, nx = self._data.shape
        bkg = np.Min([N.mean(indat[:,:nx/10,:ny/10]),
                      N.mean(indat[:,:-nx/10,:ny/10]),
                      N.mean(indat[:,:-nx/10,:-ny/10]),
                      N.mean(indat[:,:nx/10,:-ny/10])])


    def setDataSource(self, filename):
        self._data = Mrc.bindFile(filename)
        self._source = Mrc.open(filename)
        self._projection = None
        self._beadCentre = None


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
        self._beadCentre = (x + xOffset, y + yOffset)
        return self._beadCentre


    def getProjection(self):
        if self._projection is None:
            nz = self._data.shape[0]
            dz = min(30, nz / 8)
            self._projection = np.mean(self._data[nz/2 - dz : nz/2 + dz, :, :],
                                      axis=0)
        return self._projection.copy()


    def hasData(self):
        return not self._data is None


    def setBeadCentre(self, pos):
        self._beadCentre = pos


    def setPhases(self, n):
        self._phases = n
        print n


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
        label = wx.StaticText(toolbar, 
                              wx.ID_ANY, 
                              label='# phases: ',
                              style=wx.TRANSPARENT_WINDOW)
        label.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        toolbar.AddControl(label)
        phasesTool = wx.SpinCtrl(toolbar, 
                                 wx.ID_ANY,
                                 value='5',
                                 size=(48, -1),
                                 min=1,
                                 max=5,
                                 initial=5)
        phasesTool.Bind(wx.EVT_SPIN, 
                        lambda event: self.profiler.setPhases(event.GetPosition()))
        toolbar.AddControl(control=phasesTool)
        goTool = toolbar.AddSimpleTool(
                        wx.ID_ANY,
                        wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR, ICON_SIZE),
                        "Go", "Evaluate intensity profile")
        toolbar.Realize()
        self.Bind(wx.EVT_TOOL, self.loadFile, openTool)
        self.Bind(wx.EVT_TOOL, self.calculate, goTool)
        vbox.Add(toolbar, 0, border=5)        
        
        # Canvas
        self.canvas = FloatCanvas.FloatCanvas(self, size=(512,512))
        img = wx.EmptyImage(BITMAP_SIZE[0], BITMAP_SIZE[1], True)
        self.bitmap = self.canvas.AddBitmap(img, (0,0), 'cc', False)
        self.circle = self.canvas.AddCircle((0,0), 10, '#ff0000')
        self.canvas.Draw()
        self.canvas.Bind(FloatCanvas.EVT_LEFT_UP, self.onClickCanvas)
        vbox.Add(self.canvas)

        self.sb = self.CreateStatusBar()

        self.SetSizerAndFit(vbox)


    def calculate(self, event):
        if not self.profiler.hasData():
            self.sb.SetStatusText('No data loaded.')


    def loadFile(self, event):
        top = wx.GetApp().TopWindow
        dlg = wx.FileDialog(top, "Open", "", "", "",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        else:
            return
        self.profiler.setDataSource(filename)

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


    def onClickCanvas(self, event):
         # Position in pixels from upper left corner.
         pos = event.GetPosition()
         # Update profiler bead centre.
         self.profiler.setBeadCentre(pos)
         # Redraw circle to mark bead. Need to translate from pixel to world co-ords.
         self.circle.SetPoint(self.canvas.PixelToWorld(pos))
         # Update the canvas.
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