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


import cockpit.gui.guiUtils

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
        super().__init__(parent, -1, "Move Sites", *args)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, -1, "What offset should we apply?")
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

        self.controls = []
        for label in ('X', 'Y', 'Z'):
            self.controls.append(cockpit.gui.guiUtils.addLabeledInput(
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
