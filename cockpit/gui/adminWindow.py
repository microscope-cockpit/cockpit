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

import gui.guiUtils
import gui.mainWindow
import gui.mosaic.window
import util.user
import util.userConfig

## This module handles various administrator capabilities.

class AdminWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)

        self.panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer = wx.BoxSizer(wx.VERTICAL)
        for label, action, helpString in [
                ("Make window positions default", self.onMakeWindowsDefault,
                 "Record the current window positions " +
                 "and make them be the default for all new users."),
                ("Bring all windows to center display", self.onCenterWindows,
                 "Move all of the windows to the upper-left corner of the " +
                 "main display; useful if some windows are off the display " +
                 "entirely.")]:
            buttonSizer.Add(self.makeButton(label, action, helpString))
        sizer.Add(buttonSizer, 0, wx.ALL, 5)

        userSizer = wx.BoxSizer(wx.VERTICAL)
        userSizer.Add(wx.StaticText(self.panel, -1, "Current users:"))
        self.userBox = wx.ListBox(self.panel,
                style = wx.LB_SINGLE, size = (-1, 200))
        for user in reversed(util.user.getUsers()):
            self.userBox.Insert(user, 0)
        userSizer.Add(self.userBox)
        userSizer.Add(self.makeButton("Add new user", self.onAddUser,
                "Create a new user account."))
        userSizer.Add(self.makeButton("Delete user", self.onDeleteUser,
                "Delete a user's account."))
        
        sizer.Add(userSizer, 0, wx.ALL, 5)

        self.panel.SetSizerAndFit(sizer)
        self.SetClientSize(self.panel.GetSize())


    ## Simple helper function.
    def makeButton(self, label, action, helpString):
        button = wx.Button(self.panel, -1, label)
        button.SetToolTip(wx.ToolTip(helpString))
        button.Bind(wx.EVT_BUTTON, action)
        return button


    ## Record the current window positions/sizes and make them be the defaults
    # for all new users.
    def onMakeWindowsDefault(self, event = None):
        windows = wx.GetTopLevelWindows()
        positions = dict([(w.GetTitle(), tuple(w.GetPosition())) for w in windows])
        print ("Saving positions as",positions)
        util.userConfig.setValue('defaultWindowPositions',
                positions, isGlobal = True)
        # The main window gets saved separately. See MainWindow.onMove for why.
        util.userConfig.setValue('defaultMainWindowPosition',
                tuple(gui.mainWindow.window.GetPosition()), isGlobal = True)
        # The mosaic window gets its rect saved, not its position.
        util.userConfig.setValue('defaultMosaicWindowRect',
                tuple(gui.mosaic.window.window.GetRect()), isGlobal = True)


    ## Move all windows so their upper-left corners are at (0, 0).
    def onCenterWindows(self, event = None):
        for window in wx.GetTopLevelWindows():
            window.SetPosition((0, 0))


    ## Prompt for a name for a new user, then create the account.
    def onAddUser(self, event = None):
        text = wx.GetTextFromUser("Please enter the new user's name")
        if not text:
            return
        util.user.createUser(text)
        self.userBox.Insert(text, 0)


    ## Prompt for confirmation, then delete the currently-selected user.
    def onDeleteUser(self, event = None):
        if not self.userBox.GetSelection():
            # No selected user.
            return
        if not gui.guiUtils.getUserPermission(
                "Are you sure you want to delete this account?",
                "Please confirm"):
            return
        user = self.userBox.GetStringSelection()
        util.user.deleteUser(user)
        self.userBox.Delete(self.userBox.GetSelection())



def makeWindow():
    AdminWindow(None).Show()

    
