#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
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

import wx.py.shell

class ShellWindow(wx.py.shell.ShellFrame):
    SHOW_DEFAULT = False
    LIST_AS_COCKPIT_WINDOW = True

def makeWindow(parent):
    window = ShellWindow(parent)
    window.shell.run('import wx')
    window.shell.run('depot = wx.GetApp().Depot')
    # Default icon for the ShellFrame is the PyCrust, so replace it.
    window.SetIcon(parent.GetIcon())
