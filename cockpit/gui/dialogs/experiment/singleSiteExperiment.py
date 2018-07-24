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

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


import wx
from . import experimentConfigPanel
from cockpit.gui.guiUtils import EVT_COCKPIT_VALIDATION_ERROR

## A simple wrapper around the ExperimentConfigPanel class.
class SingleSiteExperimentDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent,
                title = "OMX single-site experiment",
                style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetExtraStyle(wx.WS_EX_VALIDATE_RECURSIVELY)
        self.Bind(EVT_COCKPIT_VALIDATION_ERROR, self.onValidationError)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        ## Contains all the actual UI elements beyond the dialog window itself.
        self.panel = experimentConfigPanel.ExperimentConfigPanel(self,
                resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onReset)
        self.sizer.Add(self.panel)
        
        self.buttonBox = wx.BoxSizer(wx.HORIZONTAL)

        button = wx.Button(self, -1, "Reset")
        button.SetToolTip(wx.ToolTip("Reload this window with all default values"))
        button.Bind(wx.EVT_BUTTON, self.onReset)
        self.buttonBox.Add(button, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.buttonBox.Add((1, 1), 1, wx.EXPAND)

        button = wx.Button(self, wx.ID_CANCEL, "Cancel")
        self.buttonBox.Add(button, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        
        button = wx.Button(self, wx.ID_OK, "Start")
        button.SetToolTip(wx.ToolTip("Start the experiment"))
        button.Bind(wx.EVT_BUTTON, self.onStart)
        self.buttonBox.Add(button, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.sizer.Add(self.buttonBox, 1, wx.EXPAND)

        self.statusbar = wx.StaticText(self, -1, name="status bar",
                                       style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
        self.sizer.Add(self.statusbar, 0, wx.EXPAND)

        self.SetSizerAndFit(self.sizer)


    def onValidationError(self, evt):
        self.statusbar.SetLabel("Invalid value for %s." % evt.control)


    ## Our experiment panel resized itself.
    def onExperimentPanelResize(self, panel):
        self.SetSizerAndFit(self.sizer)


    ## Attempt to run the experiment. If the testrun fails, report why.
    def onStart(self, event = None):
        self.statusbar.SetLabel('')
        if not self.Validate():
            return
        message = self.panel.runExperiment()
        if message is not None:
            wx.MessageBox("The experiment cannot be run:\n%s" % message,
                    "Error", wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
            return
        else:
            self.Hide()


    ## Blow away the experiment panel and recreate it from scratch.
    def onReset(self, event = None):
        self.sizer.Remove(self.panel)
        self.panel.Destroy()
        self.panel = experimentConfigPanel.ExperimentConfigPanel(self,
                resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onReset)
        self.sizer.Prepend(self.panel)
        self.sizer.Layout()
        self.Refresh()
        self.SetSizerAndFit(self.sizer)
        return self.panel
        
        


## Global singleton
dialog = None


def showDialog(parent):
    global dialog
    if not dialog:
        dialog = SingleSiteExperimentDialog(parent)
    dialog.Show()
