#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.


"""SIM intensity profiling tool.

This can be used on its own from the command line, or can be included
as part of another wx app.
"""


from contextlib import contextmanager
import gc
from itertools import chain
from cockpit.util.Mrc import Mrc
import numpy as np
from operator import add
import wx
from wx.lib.floatcanvas import FloatCanvas
import wx.lib.plot as plot


ICON_SIZE = (16,16)
BITMAP_SIZE = (512,512)


class IntensityProfiler:
    """A class to profile intensity and store calculation variables."""
    def __init__(self):
        self._data = None
        self._dataSource = None
        self._projection = None
        self._beadCentre = None
        self._halfWidth = 25
        self._phases = 5
        self.results = None

    @contextmanager
    def openData(self):
        """A context manager to avoid holding files open.

        Mrc.bindFile uses numpy mem-mapping. The only way to
        close a mem-mapped file is to delete all references to
        the memmap object, which will then be cleaned up by
        the garbage collector.
        """
        try:
            # Test if this is a reentrant call.
            isOutermostCall = self._data is None
            if isOutermostCall:
                src = self._dataSource
                self._data = Mrc(src, 'r').data_withMrc(src)
            yield
        except IOError:
            dlg = wx.MessageDialog(wx.GetTopLevelWindows()[0],
                            "Could not open data file: it may have been moved or deleted.",
                            caption="IO Error",
                            style = wx.OK)
            dlg.ShowModal()
            yield
        finally:
            if isOutermostCall:
                self._data = None
                gc.collect()

    def calculateInstensity(self):
        """Do the calculation."""
        if self._dataSource is None:
                return False
        with self.openData():
            if self._beadCentre is None:
                self.guessBeadCentre()
            nPhases = self._phases
            nz, ny, nx = self._data.shape
            if not self._halfWidth:
                self.setHalfWidth(min(nx/10, ny/10))
            halfWidth = self.getHalfWidth()
            peakx, peaky = self._beadCentre
            # Use a the fifth of the data around the bead, or to edge of dataset.
            dataSubset = self._data[:,
                              max(0, peaky-halfWidth):min(ny, peaky+halfWidth),
                              max(0, peakx-halfWidth):min(nx, peakx+halfWidth)]
            # Estimate background from image corners.
            bkg = np.min([np.mean(self._data[:,:nx//10,:ny//10]),
                          np.mean(self._data[:,:-nx//10,:ny//10]),
                          np.mean(self._data[:,:-nx//10,:-ny//10]),
                          np.mean(self._data[:,:nx//10,:-ny//10])])
            phaseArr = np.sum(np.sum(dataSubset - bkg, axis=2), axis=1)
            phaseArr = np.reshape(phaseArr, (-1, nPhases)).astype(np.float32)
            sepArr = np.dot(self.sepmatrix(), phaseArr.transpose())
            mag = np.zeros((nPhases//2 + 1, nz//nPhases)).astype(np.float32)
            phi = np.zeros((nPhases//2 + 1, nz//nPhases)).astype(np.float32)
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
        self._dataSource = filename
        self._projection = None
        self._beadCentre = None
        self._results = None
        with self.openData():
            self.zDelta = self._data.Mrc.hdr.d[-1]
            self.setHalfWidth(min(self._data.shape[1:])/10)

    def guessBeadCentre(self, refine=True):
        """Estimate the bead centre from position of maximum data value.

        refine =
            True: search around current _beadCentre
            False: search around middle of dataset.
        """
        if self._dataSource is None:
            return
        with self.openData():
            nz, ny, nx = self._data.shape
            if self._beadCentre is None or not refine:
                # Search around centre of dataset.
                middle = self._data[:,
                                    3*ny // 8 : 5*ny // 8,
                                    3*nx // 8 : 5*nx // 8]
                xOffset = nx//2 - middle.shape[-1]//2
                yOffset = ny//2 - middle.shape[-2]//2
            else:
                # Search around current _beadCentre.
                n = 24
                x0, y0 = self._beadCentre
                middle = self._data[:,
                                    y0 - n//2 : y0 + n//2,
                                    x0 - n//2 : x0 + n//2]
                xOffset = x0 - n//2
                yOffset = y0 - n//2
            peakPosition = np.argmax(middle)
            (z, y, x) = np.unravel_index(peakPosition, middle.shape)
            self._beadCentre = (x + xOffset, y + yOffset)
            return self._beadCentre

    def getProjection(self):
        """Calculates a Z-projection and returns a copy."""
        if self._projection is None:
            with self.openData():
                nz = self._data.shape[0]
                dz = min(100, nz // 3)
                subset = self._data[nz//2 - dz : nz//2 + dz, :, :].copy()
            # Single step np.mean leaves open refs to self._data, for some reason.
            #self._projection = np.mean(subset, axis=0)
            # Create empty array and use indexed mean to avoid stray refs.
            self._projection = np.zeros(subset.shape[1:3])
            self._projection[:,:] = np.mean(subset, axis=0)
        return self._projection

    def hasData(self):
        """Do I have data?"""
        return not self._dataSource is None

    def sepmatrix(self):
        """Return SIM separation matrix.

        Depends on self._phases."""
        nphases = self._phases
        sepmat = np.zeros((nphases, nphases)).astype(np.float32)
        norders = (nphases+1)//2
        phi = 2*np.pi / nphases
        for j in range(nphases):
            sepmat[0, j] = 1.0 / nphases
            for order in range(1, norders):
                sepmat[2*order-1,j] = 2.0 * np.cos(j*order*phi)/nphases
                sepmat[2*order  ,j] = 2.0 * np.sin(j*order*phi)/nphases
        return sepmat

    def getBeadCentre(self):
        """Return the bead centre co-ordinates."""
        return self._beadCentre

    def setBeadCentre(self, pos):
        """Set the bead centre to a client-provided value."""
        self._beadCentre = pos

    def getHalfWidth(self):
        """Return the box half width."""
        return self._halfWidth

    def setHalfWidth(self, val):
        """Set the box half width."""
        self._halfWidth = int(val)

    def setPhases(self, n):
        """Set the number of phases to use in sepmatrix."""
        self._phases = n


class IntensityProfilerFrame(wx.Frame):
    """This class provides a UI for IntensityProfiler."""
    SHOW_DEFAULT = False
    def __init__(self, parent=None):
        super().__init__(parent, title="SIM intensity profile")
        self.profiler = IntensityProfiler()
        # Outermost sizer.
        vbox = wx.BoxSizer(wx.VERTICAL)

        ## Toolbar
        toolbar = wx.ToolBar(self, -1)
        # Open file
        openTool = toolbar.AddTool(wx.ID_ANY,
                                   "Open",
                                   wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN,
                                                            wx.ART_TOOLBAR,
                                                            ICON_SIZE),
                                   shortHelp="Open a dataset.")
        toolbar.AddSeparator()
        # Number of phases
        phaseLabel = wx.StaticText(toolbar,
                              wx.ID_ANY,
                              label='# phases: ',
                              style=wx.TRANSPARENT_WINDOW)
        phaseLabel.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        toolbar.AddControl(phaseLabel)
        phasesTool = wx.SpinCtrl(toolbar,
                                 wx.ID_ANY,
                                 value='5',
                                 size=(48, -1),
                                 min=1,
                                 max=5,
                                 initial=5,
                                 style=wx.SP_ARROW_KEYS|wx.TE_PROCESS_ENTER)
        phasesTool.Bind(wx.EVT_SPINCTRL,
                        lambda event: self.profiler.setPhases(event.GetInt()))
        phasesTool.Bind(wx.EVT_TEXT_ENTER,
                        lambda event: self.profiler.setPhases(event.GetInt()))
        toolbar.AddControl(control=phasesTool)
        toolbar.AddSeparator()
        # Box size.
        boxLabel = wx.StaticText(toolbar,
                              wx.ID_ANY,
                              label='box size: ',
                              style=wx.TRANSPARENT_WINDOW)
        boxLabel.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        toolbar.AddControl(boxLabel)
        boxTool = wx.SpinCtrl(toolbar,
                              wx.ID_ANY,
                              value='25',
                              size=(48, -1),
                              min=10,
                              max=2**16,
                              initial=25,
                              style = wx.SP_ARROW_KEYS | wx.TE_PROCESS_ENTER)
        boxTool.Bind(wx.EVT_TEXT_ENTER,
                        lambda event: self.setBoxSize(event.GetInt()))
        boxTool.Bind(wx.EVT_SPINCTRL,
                        lambda event: self.setBoxSize(event.GetInt()))
        toolbar.AddControl(control=boxTool)
        self.boxTool = boxTool
        toolbar.AddSeparator()
        # Calculate profile.
        goTool = toolbar.AddTool(wx.ID_ANY,
                                 "Go",
                                 wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR, ICON_SIZE),
                                 shortHelp="Evaluate intensity profile")
        toolbar.Realize()
        self.Bind(wx.EVT_TOOL, self.loadFile, openTool)
        self.Bind(wx.EVT_TOOL, self.calculate, goTool)
        vbox.Add(toolbar, 0, border=5)

        ## Canvases
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        # Image canvas
        self.canvas = FloatCanvas.FloatCanvas(self, size=(512,512),
                                              style = wx.WANTS_CHARS)

        img = wx.Image(BITMAP_SIZE[0], BITMAP_SIZE[1], clear=True)
        self.bitmap = self.canvas.AddBitmap(img, (0,0), 'cc', False)
        self.circle = self.canvas.AddCircle((0,0), 10, '#ff0000')
        self.rectangle = self.canvas.AddRectangle((0,0), (20,20), '#ff0000')
        self.canvas.Bind(FloatCanvas.EVT_LEFT_UP, self.onClickCanvas)
        hbox.Add(self.canvas)
        self.canvas.Bind(wx.EVT_CHAR, self.onKeys)
        # Plot canvas
        self.plotCanvas = plot.PlotCanvas(self, wx.ID_ANY)
        self.plotCanvas.canvas.Bind(wx.EVT_LEFT_UP, self.onClickPlotCanvas)
        self.plotCanvas.MinSize=(512,512)
        self.plotCanvas.SetSize((512,512))
        hbox.Add(self.plotCanvas)

        vbox.Add(hbox)

        ## Status bar.
        self.sb = self.CreateStatusBar()
        self.sb.SetFieldsCount(2)
        self.sb.DefaultText = 'Cursors, PgUp/Dn to set box. '        \
                              '(Shift) space to (global) find bead. '\
                              'Enter or Return to calculate.'
        self.sb.SetStatusText(self.sb.DefaultText)
        self.SetSizerAndFit(vbox)

        toolbar.SetToolLongHelp(0, self.sb.DefaultText)

        self.boxTool = boxTool

    def calculate(self, event=None):
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
        peak = plot.PolyLine(list(zip(peakX, peakY)), colour='red')
        # Average intensity over a few XY points around the peak.
        # The raw intensity plot can vary greatly when the z-profile is taken
        # just one pixel away; this average plot can help show if a dip in the
        # raw data is a feature of the bead, or due to noise.
        avgY = self.profiler.results['avg'][1:]
        avgX = np.arange(len(avgY)) * (self.profiler.zDelta or 1)
        avg = plot.PolyLine(list(zip(avgX, avgY)), colour='red', style=wx.DOT)
        # First order.
        firstY = self.profiler.results['mag'][1,1:]
        firstX = np.arange(len(firstY)) * (self.profiler.zDelta or 1)
        first = plot.PolyLine(list(zip(firstX, firstY)), colour='green')
        # Second order.
        secondY = self.profiler.results['mag'][2,1:]
        secondX = np.arange(len(secondY)) * (self.profiler.zDelta or 1)
        second = plot.PolyLine(list(zip(secondX, secondY)), colour='blue')
        # Add line graphs to a graphics context.
        if self.profiler.zDelta is None:
            xLabel = 'Z slice'
        else:
            xLabel = 'Z'
        gc = plot.PlotGraphics([peak, avg, first, second],
                               'Intensity profiles', xLabel, 'counts')
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
            self.sb.SetStatusText(self.sb.DefaultText)
        else:
            self.sb.SetStatusText('Cancelled - no data loaded.')
            return
        # Set the profiler data source .
        self.profiler.setDataSource(filename)
        self.boxTool.Value = self.profiler.getHalfWidth()

        # Guess a bead position
        xpos, ypos = self.profiler.guessBeadCentre()
        # Move indicator circle to the bead position.
        self.circle.SetPoint(self.canvas.PixelToWorld((xpos, ypos)))

        # Update the bitmap.
        proj = self.profiler.getProjection()
        proj -= np.min(proj)
        proj /= np.max(proj)
        proj = (proj * 255).astype(np.uint8)
        img = np.dstack((proj, proj, proj))
        nx, ny = proj.shape
        self.bitmap.Bitmap.SetSize((nx,ny))
        self.bitmap.Bitmap.CopyFromBuffer(img.tostring())

        # Update the canvas.
        self.plotCanvas.Clear()
        self.updateCanvas()

    def onClickPlotCanvas(self, event):
        """Show the mouse graph-space coords in status bar."""
        pos = event.GetPosition()
        uv = self.plotCanvas.PositionScreenToUser(pos)
        #self.sb.SetStatusText('u:%3f, v:%3f' % uv, 1)
        self.sb.SetStatusText('Z: {0[0]:3.3g},  counts: {0[1]:3.3g}'.format(uv), 1)

    def onClickCanvas(self, event):
        """Respond to click to choose a new bead position."""
        # Position in pixels from upper left corner.
        pos = event.GetPosition()
        # Update profiler bead centre.
        self.profiler.setBeadCentre(pos)
        # Update the canvas.
        self.updateCanvas()

    def updateCanvas(self):
        pos = self.profiler.getBeadCentre()
        w = self.profiler.getHalfWidth()
        # Translate from pixel to world co-ords.
        centre = self.canvas.PixelToWorld(pos)
        wh = self.canvas.ScalePixelToWorld((w,w))
        xy = centre - wh
        # Redraw circle to mark bead.
        self.circle.SetPoint(centre)
        # Redraw the rectangle to mark data subset.
        self.rectangle.SetShape(xy, 2 * wh)
        # Redraw.
        self.canvas.Draw(Force=True)

    def setBoxSize(self, value):
        self.profiler.setHalfWidth(value)
        # Update the canvas.
        self.updateCanvas()

    def onKeys(self, event):
        keys= {'move': [wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_UP, wx.WXK_DOWN,],
               'size': [wx.WXK_PAGEDOWN, wx.WXK_PAGEUP],
               'calc': [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER],
               'find': [wx.WXK_SPACE, wx.WXK_NUMPAD0, wx.WXK_NUMPAD_DECIMAL],}

        keycode = event.KeyCode
        keymod = event.GetModifiers()
        if keycode not in [c for c in chain.from_iterable(keys.values())]:
            return
        elif keycode in keys['move']:
            delta = [1, 6][keymod & wx.MOD_SHIFT > 0]
            # Map keys to position changes.
            dPos = {wx.WXK_LEFT:  (-delta, 0),
                    wx.WXK_RIGHT: (delta, 0),
                    wx.WXK_DOWN:  (0, delta),
                    wx.WXK_UP:    (0, -delta),}

            pos = self.profiler.getBeadCentre()
            newPos = list(map(add, pos, dPos[keycode]))

            self.profiler.setBeadCentre(newPos)
            self.updateCanvas()
        elif keycode in keys['size']:
            if keycode == wx.WXK_PAGEUP:
                delta = [1, 6][keymod & wx.MOD_SHIFT > 0]
            else:
                delta = [-1, -6][keymod & wx.MOD_SHIFT > 0]
            # Update spin control.
            self.boxTool.SetValue(self.boxTool.GetValue() + delta)
            # Set the box size. Spin control may limit value so use GetValue.
            self.setBoxSize(self.boxTool.GetValue())
        elif keycode in keys['calc']:
            self.calculate()
        elif keycode in keys['find']:
            pos = self.profiler.guessBeadCentre(refine=keymod & wx.MOD_SHIFT == 0)
            self.updateCanvas()


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
    window = IntensityProfilerFrame(parent)


if __name__ == '__main__':
    main()
