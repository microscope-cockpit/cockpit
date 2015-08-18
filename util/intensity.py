#!/usr/bin/python
# -*- coding: UTF8   -*-
"""SIM intensity profiling tool.

Copyright 2015 Mick Phillips (mick.phillips at gmail dot com)
and Ian Dobbie.
Based on a command-line utility by Lin Shao.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
=============================================================================

This can be used on its own from the command line, or can be included
as part of another wx app.
"""


import matplotlib.pyplot as plt
import Mrc
import numpy as np
import sys
import wx
from wx.lib.floatcanvas import FloatCanvas
import wx.lib.plot as plot

ICON_SIZE = (16,16)
BITMAP_SIZE = (512,512)


class IntensityProfiler(object):
    """A class to profile intensity and store calculation variables."""
    def __init__(self):
        self._data = None
        self._projection = None
        self._beadCntre = None
        self._phases = 5
        self.results = None


    def calculateInstensity(self):
        """Do the calculation."""
        if self._data is None:
            return False
        if self._beadCentre is None:
            self.guessBeadCentre()
        nPhases = self._phases
        nz, ny, nx = self._data.shape
        peakx, peaky = self._beadCentre
        # Use a the fifth of the data around the bead, or to edge of dataset.
        dataSubset = self._data[:,
                                max(0, peaky - ny/10) : min(ny, peaky + ny/10),
                                max(0, peakx - nx/10) : min(nx, peakx + nx/10)]
        # Estimate background from image corners.
        bkg = np.min([np.mean(self._data[:,:nx/10,:ny/10]),
                      np.mean(self._data[:,:-nx/10,:ny/10]),
                      np.mean(self._data[:,:-nx/10,:-ny/10]),
                      np.mean(self._data[:,:nx/10,:-ny/10])])

        # phaseArr = np.sum(np.sum(self._data - bkg, axis=2), axis=1)
        phaseArr = np.sum(np.sum(dataSubset - bkg, axis=2), axis=1)
        phaseArr = np.reshape(phaseArr, (-1, nPhases)).astype(np.float32)
        sepArr = np.dot(self.sepmatrix(), phaseArr.transpose())
        mag = np.zeros((nPhases/2 + 1, nz/nPhases)).astype(np.float32)
        phi = np.zeros((nPhases/2 + 1, nz/nPhases)).astype(np.float32)
        mag[0] = sepArr[0]

        for order in range (1,3):
            mag[order] = np.sqrt(sepArr[2*order-1]**2 + sepArr[2*order]**2)
            phi[order] = np.arctan2(sepArr[2*order], sepArr[2*order-1])
        # Average a few points around the peak
        beadAverage = np.average(np.average(
                          self._data[:, peaky-2:peaky+2, peakx-2:peakx+2],
                          axis=2), axis=1)
        avgPeak = np.reshape(beadAverage, (-1, nPhases))
        avgPeak = np.average(avgPeak, 1)
        avgPeak -= avgPeak.min()
        avgPeak *= mag[1].max() / avgPeak.max()

        peak = np.reshape(self._data[:,peaky,peakx], (-1, nPhases))
        peak = np.average(peak, 1)
        peak -= peak.min()
        peak *= mag[1].max() / peak.max()

        self.results = dict(peak=peak,
                            avg=avgPeak,
                            mag=mag,
                            phi=phi,
                            sep=sepArr)


    def setDataSource(self, filename):
        """Set data source, clearing invalidated variables."""
        self._data = Mrc.bindFile(filename)
        # Mrc.py version conflict.
        # With cockpit data, Mrc.open from cockpit/util/Mrc.py works just fine,
        # but local Mrc.py fails. There are no version numbers, so I have no idea
        # which is 'current'.
        try:
            self._source = Mrc.open(filename)
            self.zDelta = self._source.hdr.d[-1]
        except:
            self.zDelta = None
        self._projection = None
        self._beadCentre = None
        self._results = None


    def guessBeadCentre(self):
        """Estimate the bead centre from position of maximum data value."""
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
        """Calculates a Z-projection and returns a copy."""
        if self._projection is None:
            nz = self._data.shape[0]
            dz = min(100, nz / 3)
            self._projection = np.mean(self._data[nz/2 - dz : nz/2 + dz, :, :],
                                      axis=0)
        return self._projection.copy()


    def hasData(self):
        """Do I have data?"""
        return not self._data is None


    def sepmatrix(self):
        """Return SIM separation matrix.

        Depends on self._phases."""
        nphases = self._phases
        sepmat = np.zeros((nphases,nphases)).astype(np.float32)
        norders = (nphases+1)/2
        phi = 2*np.pi / nphases
        for j in range(nphases):
            sepmat[0, j] = 1.0/nphases
            for order in range(1,norders):
                sepmat[2*order-1,j] = 2.0 * np.cos(j*order*phi)/nphases
                sepmat[2*order  ,j] = 2.0 * np.sin(j*order*phi)/nphases
        return sepmat


    def setBeadCentre(self, pos):
        """Set the bead centre to a client-provided value."""
        self._beadCentre = pos


    def setPhases(self, n):
        """Set the number of phases to use in sepmatrix."""
        self._phases = n


class IntensityProfilerFrame(wx.Frame):
    """This class provides a UI for IntensityProfiler."""
    def __init__(self, parent=None):
        super(IntensityProfilerFrame, self).__init__(parent, title="SIM intensity profile")
        self.profiler = IntensityProfiler()

        # Outermost sizer.
        vbox = wx.BoxSizer(wx.VERTICAL)

        ## Toolbar
        toolbar = wx.ToolBar(self, -1)
        # Open file
        openTool = toolbar.AddSimpleTool(
                        wx.ID_ANY,
                        wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, ICON_SIZE),
                        "Open", "Open a dataset")
        toolbar.AddSeparator()
        # Number of phases
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
        # Calculate profile.
        goTool = toolbar.AddSimpleTool(
                        wx.ID_ANY,
                        wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR, ICON_SIZE),
                        "Go", "Evaluate intensity profile")
        toolbar.Realize()
        self.Bind(wx.EVT_TOOL, self.loadFile, openTool)
        self.Bind(wx.EVT_TOOL, self.calculate, goTool)
        vbox.Add(toolbar, 0, border=5)

        ## Canvases
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        # Image canvas
        self.canvas = FloatCanvas.FloatCanvas(self, size=(512,512))
        img = wx.EmptyImage(BITMAP_SIZE[0], BITMAP_SIZE[1], True)
        self.bitmap = self.canvas.AddBitmap(img, (0,0), 'cc', False)
        self.circle = self.canvas.AddCircle((0,0), 10, '#ff0000')
        self.canvas.Draw()
        self.canvas.Bind(FloatCanvas.EVT_LEFT_UP, self.onClickCanvas)
        hbox.Add(self.canvas)
        # Plot canvas
        self.plotCanvas = plot.PlotCanvas(self, wx.ID_ANY, pos=(-1,-1))
        self.plotCanvas.MinSize=(512,512)
        self.plotCanvas.SetSize((512,512))
        hbox.Add(self.plotCanvas)

        vbox.Add(hbox)

        ## Status bar.
        self.sb = self.CreateStatusBar()

        self.SetSizerAndFit(vbox)


    def calculate(self, event):
        """Calculate the profile."""
        # Check that the profiler has data.
        if not self.profiler.hasData():
            self.sb.SetStatusText('No data loaded.')
        # Do the calculation
        if self.profiler.calculateInstensity() is False:
            return
        ## Generate line graphs
        # Raw intensity at one point in XY.
        peakY = self.profiler.results['peak'][1:]
        peakX = np.arange(len(peakY)) * (self.profiler.zDelta or 1)
        peak = plot.PolyLine(zip(peakX, peakY), colour='red')
        # Average intensity over a few XY points around the peak.
        # The raw intensity plot can vary greatly when the z-profile is taken
        # just one pixel away; this average plot can help show if a dip in the
        # raw data is a feature of the bead, or due to noise.
        avgY = self.profiler.results['avg'][1:]
        avgX = np.arange(len(avgY)) * (self.profiler.zDelta or 1)
        avg = plot.PolyLine(zip(avgX, avgY), colour='red', style=wx.DOT)
        # First order.
        firstY = self.profiler.results['mag'][1,1:]
        firstX = np.arange(len(firstY)) * (self.profiler.zDelta or 1)
        first = plot.PolyLine(zip(firstX, firstY), colour='green')
        # Second order.
        secondY = self.profiler.results['mag'][2,1:]
        secondX = np.arange(len(secondY)) * (self.profiler.zDelta or 1)
        second = plot.PolyLine(zip(secondX, secondY), colour='blue')
        # Add line graphs to a graphics context.
        if self.profiler.zDelta is None:
            xLabel = 'Z slice'
        else:
            xLabel = 'Z'
        gc = plot.PlotGraphics([peak, avg, first, second],
                               'Intensity profiles', xLabel, 'arb. units')
        # Clear any old graphs.
        self.plotCanvas.Clear()
        # Draw the graphics context.
        self.plotCanvas.Draw(gc)


    def loadFile(self, event):
        """Open a data file."""
        ## Display the file chooser.
        top = wx.GetApp().TopWindow
        dlg = wx.FileDialog(top, "Open", "", "", "",
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        else:
            return
        # Set the profiler data source .
        self.profiler.setDataSource(filename)

        # Guess a bead position
        xpos, ypos = self.profiler.guessBeadCentre()
        # Move indicator circle to the bead position.
        self.circle.SetPoint(self.canvas.PixelToWorld((xpos, ypos)))

        # Update the bitmap.
        proj = self.profiler.getProjection()
        proj -= np.min(proj)
        proj /= np.max(proj)
        proj = (proj * 255).astype(np.uint8)
        d = range(-10,-3) + range(3, 10)
        img = np.dstack((proj, proj, proj))
        nx, ny = proj.shape
        self.bitmap.Bitmap.SetSize((nx,ny))
        self.bitmap.Bitmap.CopyFromBuffer(img.tostring())

        # Update the canvas.
        self.plotCanvas.Clear()
        self.canvas.Draw(Force=True)


    def onClickCanvas(self, event):
        """Respond to click to choose a new bead position."""
        # Position in pixels from upper left corner.
        pos = event.GetPosition()
        # Update profiler bead centre.
        self.profiler.setBeadCentre(pos)
        # Redraw circle to mark bead. Need to translate from pixel to world co-ords.
        self.circle.SetPoint(self.canvas.PixelToWorld(pos))
        # Update the canvas.
        self.canvas.Draw(Force=True)


def main():
    """Run as a standalone app."""
    import wx.lib.inspection
    app = wx.App(False)
    ip = IntensityProfilerFrame()
    ip.Show()
    wx.lib.inspection.InspectionTool().Show()
    app.MainLoop()


def makeWindow(parent):
    """Call from another app to get a single window instance."""
    global window
    window = IntensityProfilerFrame(parent)
    #window.Bind(wx.EVT_CLOSE, lambda event: window.Hide())
    #return window


if __name__ == '__main__':
    main()