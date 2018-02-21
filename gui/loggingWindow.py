import sys
import wx
import wx.aui

import util.logger



## This class provides a window that displays two text panels which capture
# output (stdout and stderr) from the rest of the program. This simplifies
# debugging in many ways.
class LoggingWindow(wx.Frame):
    def __init__(self, parent, title = 'Logging panels',
                 style = wx.CAPTION | wx.MAXIMIZE_BOX | wx.FRAME_TOOL_WINDOW | wx.RESIZE_BORDER):
        wx.Frame.__init__(self, parent, title = title, style = style)

        self.auiManager = wx.aui.AuiManager()
        self.auiManager.SetManagedWindow(self)

        ## Text control that captures standard output.
        self.stdOut = wx.TextCtrl(self, 6465, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        ## Text control that captures standard error.
        self.stdErr = wx.TextCtrl(self, 6265, style=wx.TE_MULTILINE | wx.BORDER_SUNKEN)
        ## Cached text, awaiting addition to the logs. If we just log everything
        # as it comes in, then we get tons of newlines we don't want.
        self.textCache = ''

        # HACK: enforce that writing to these controls only happens in the
        # main thread.
        self.stdOut.write = lambda *args: self.write(self.stdOut, *args)
        self.stdErr.write = lambda *args: self.write(self.stdErr, *args)

        sys.stdout = self.stdOut
        sys.stderr = self.stdErr

        self.auiManager.AddPane(self.stdErr, wx.aui.AuiPaneInfo().Caption("Standard error").CloseButton(False).Top().MinSize((-1, 194)))
        self.auiManager.AddPane(self.stdOut, wx.aui.AuiPaneInfo().Caption("Standard out").CloseButton(False).Center().MinSize((-1, 194)))

        self.auiManager.Update()

        self.SetSize((600, 460))


    ## Send text to one of our output boxes, and also log that text.
    def write(self, target, *args):
        #wx.CallAfter(target.AppendText, *args)
        target.AppendText(*args)
        self.textCache += ' '.join(map(str, args))
        if '\n' in self.textCache:
            # Ended a line; send the text to the logs, minus any trailing
            # whitespace (since the logs add their own trailing newline.
            if target is self.stdOut:
                util.logger.log.debug(self.textCache.rstrip())
            else:
                util.logger.log.error(self.textCache.rstrip())
            self.textCache = ''



## Global singleton
window = None


def makeWindow(parent):
    global window
    window = LoggingWindow(parent)
    window.Show()

## Retrieve the contents of the stdout control.
def getStdOut():
    return window.stdOut.GetValue()

## Retrieve the contents of the stderr control.
def getStdErr():
    return window.stdErr.GetValue()
