##This is a window for selecting the ROI for interferometry
# !/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2019 Nick Hall (nicholas.hall@dtc.ox.ac.uk)
# Copyright 2019 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Display a window that allows the user to select a circular area."""

import numpy as np
import wx

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

class viewCharAssay(wx.Frame):
    def __init__(self, characterisation_assay):
        wx.Frame.__init__(self, None, -1, 'Characterisation Asssay. '
                                          'Mean Zernike reconstruction accuracy: %0.5f'
                          % (np.mean(np.diag(characterisation_assay))))

        self.Sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.figure = Figure()
        self.axes1 = self.figure.add_subplot(111)
        self.canvas1 = FigureCanvas(self, -1, self.figure)
        self.Sizer.Add(self.canvas1, 1, wx.LEFT | wx.TOP | wx.GROW)

        self.figure = Figure()
        self.axes2 = self.figure.add_subplot(111)
        self.canvas2 = FigureCanvas(self, -1, self.figure)
        self.Sizer.Add(self.canvas2, 1, wx.LEFT | wx.TOP | wx.GROW)


        self.Fit()
        self.doPlotting(characterisation_assay)

    def doPlotting(self, image):
        self.axes1.imshow(image)
        self.axes2.plot(np.diag(image))