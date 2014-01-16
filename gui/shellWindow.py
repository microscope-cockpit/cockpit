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
            self.parent.shell.push('import util.datadoc; %s = util.datadoc.DataDoc("%s")' % (variable, filename))
                


def makeWindow(parent):
    shell = ShellWindow(parent, title = "Python shell",
            style = wx.CAPTION | wx.MAXIMIZE_BOX | wx.FRAME_TOOL_WINDOW | wx.RESIZE_BORDER)
