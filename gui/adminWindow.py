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
        print "Saving positions as",positions
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

    
