#!/usr/bin/env python
# -*- coding: utf-8 -*-

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


## This module handles creating the in-program Python REPL
# (read-eval-print loop) shell.

import os
import wx
import wx.py



class ShellWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)

        self.shell = wx.py.shell.Shell(self)
        self.SetRect((0, 300, 650, 550))

        self.SetDropTarget(DropTarget(self))
        self.shell.SetDropTarget(DropTarget(self))

        self.Show()



## Allow users to drag MRC files onto this window to bind them to a variable.
class DropTarget(wx.FileDropTarget):
    def __init__(self, parent):
        wx.FileDropTarget.__init__(self)
        self.parent = parent


    def OnDropFiles(self, x, y, filenames):
        for filename in filenames:
            variable = wx.GetTextFromUser("Bind the contents of %s to a variable named:" % filename)
            if not variable:
                continue
            # Stupid Windows backslashes...
            filename = filename.replace('\\', '/')
            # UGH this is a hack, but as far as I can tell there's no clean
            # way to insert variables into the shell's context.
            self.parent.shell.push('import cockpit.util.datadoc; %s = cockpit.util.datadoc.DataDoc("%s")' % (variable, filename))
                


def makeWindow(parent):
    shell = ShellWindow(parent, title = "Python shell",
            style = wx.CAPTION | wx.MAXIMIZE_BOX | wx.FRAME_TOOL_WINDOW | wx.RESIZE_BORDER)
