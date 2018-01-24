import events
import files
import gui.loggingWindow
import logger
import userConfig

import datetime
import os
import sys
import time
import traceback
import wx

## @package user
# This module contains functions related to who is currently using OMX.

## Tracks the last login time.
lastLoginTime = None
## Tracks who is currently logged in, as an index into the list of users.
curLoginID = None
## Tracks the name of the user currently logged in.
curLoginName = None

## Get a list of valid usernames, based on the names of directories to
# which data is stored.
def getUsers():
    users = []
    dataDir = files.getDataDir()
    for entry in os.listdir(dataDir):
        if os.path.isdir(os.path.join(dataDir, entry)):
            users.append(os.path.basename(entry))
    users.sort(key = str.lower)
    return users


## Ask the user what their username is, then set a variety of different
# internal settings and "reset" the program to its base state.
def login(parent):
    loginUsers = getUsers()

    dialog = wx.SingleChoiceDialog(parent,
            "Please tell me who you are", "login",
            loginUsers, wx.OK | wx.CANCEL | wx.STAY_ON_TOP)
    dialog.SetSize((400, 400))
    dialog.SetFont(wx.Font(20, wx.DEFAULT, wx.NORMAL, wx.BOLD))
    global curLoginID
    if curLoginID is not None:
        dialog.SetSelection(curLoginID)
    else:
        dialog.SetSelection(0)
    dialog.ShowModal()

    global curLoginName
    curLoginName = dialog.GetStringSelection()
    curLoginID = dialog.GetSelection()
    global lastLoginTime
    lastLoginTime = time.time()

    logger.changeFile(logger.generateLogFileName(curLoginName))
    setWindowPositions()

    userConfig.setValue('lastLoginDate', str(datetime.date.today()),
            isGlobal = True)
    events.publish("user login", curLoginName)
    dialog.Destroy()


## Move the windows to where the user wants them to be.
def setWindowPositions():
    # Imports here to fix cyclic dependancy.
    import gui.mainWindow
    import gui.mosaic.window
    # Maps window titles to their positions.
    positions = userConfig.getValue('windowPositions', default =
            userConfig.getValue('defaultWindowPositions', isGlobal = True,
            default = None))
    if positions is not None:
        for window in wx.GetTopLevelWindows():
            title = window.GetTitle()
            if title in positions:
                window.SetPosition(positions[title])
            # HACK: the camera window's title changes all the time, since
            # it includes pixel value information.
            elif 'Camera views' in title:
                for key, value in positions.iteritems():
                    if 'Camera views' in key:
                        window.SetPosition(value)
                        break
    # Special cases: the main window is stored under a different config key.
    # It flat-out doesn't exist by the time logout() is called, so we *can't*
    # get its position at that point; instead it's stored every time the
    # main window is moved.
    position = userConfig.getValue('mainWindowPosition', default =
            userConfig.getValue('defaultMainWindowPosition', isGlobal = True,
                default = None))
    if position:
        gui.mainWindow.window.SetPosition(position)
    # For the mosaic view, we want to set the rect, not the position.
    rect = userConfig.getValue('mosaicWindowRect', default =
            userConfig.getValue('defaultMosaicWindowRect', isGlobal = True,
                default = None))
    if rect:
        gui.mosaic.window.window.SetRect(rect)


## Record the current window positions. Note that this doesn't get the main
# window if this is called during logout, since at that point the main window
# no longer exists. That window's position is stored under a different key.
def saveWindowPositions():
    positions = dict([(w.GetTitle(), tuple(w.GetPosition())) for w in wx.GetTopLevelWindows()])
    userConfig.setValue('windowPositions', positions)
    logger.log.error("Saved positions %s" % positions)


## Clear a bunch of settings and make certain everything is stopped. Then
# invoke login() if reLogin is true.
def logout(shouldLoginAgain = True):
    try:
        events.publish("user abort")
        events.publish("user logout")

        saveWindowPositions()
    except Exception as e:
        logger.log.error("Error during logout: %s" % e)
        logger.log.error(traceback.format_exc())

    global lastLoginTime
    if lastLoginTime is not None:
        # This only doesn't happen if login failed.
        dt = time.time() - lastLoginTime
        hours = dt // 3600
        minutes = (dt - 60 * hours) // 60
        seconds = dt - 3600 * hours - 60 * minutes

        timeString = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.log.debug("  *** MUI logout: %s at %s after %2dH:%02dM:%02dS",
                    curLoginName, timeString, hours, minutes, seconds)
        logger.log.debug("  *** STANDARD OUTPUT FOLLOWS ***  ")
        logger.log.debug(gui.loggingWindow.getStdOut())
        logger.log.debug("  *** STANDARD ERROR FOLLOWS ***  ")
        logger.log.debug(gui.loggingWindow.getStdErr())
    else:
        logger.log.debug("  *** MUI logout: Unknown login time.")
    if shouldLoginAgain:
        login()


## Create a new user account.
def createUser(newUsername):
    os.mkdir(os.path.join(files.getDataDir(), newUsername))


## Delete a user account.
def deleteUser(username):
    os.rmdir(os.path.join(files.getDataDir(), username))


## Get the name of the current user.
def getUsername():
    return curLoginName


## Get the directory the current user's data is stored in.
def getUserSaveDir():
    return os.path.join(files.getDataDir(), curLoginName)
