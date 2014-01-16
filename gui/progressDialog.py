## This is a wrapper around the ProgressDialog class, used for when we want
# to show progress updates, but the caller is not in the main thread. It just
# uses wx.CallAfter to redirect calls to the __init__, Update, and Destroy
# methods. Of course, true ProgressDialogs have many other available functions,
# so this is not truly safe, but it's good enough for most of our uses.

import util.threads

import wx


class ProgressDialog(wx.ProgressDialog):
    @util.threads.callInMainThread
    def __init__(*args, **kwargs):
        wx.ProgressDialog.__init__(*args, **kwargs)


    @util.threads.callInMainThread
    def Update(*args, **kwargs):
        wx.ProgressDialog.Update(*args, **kwargs)


    @util.threads.callInMainThread
    def Destroy(*args, **kwargs):
        wx.ProgressDialog.Destroy(*args, **kwargs)
