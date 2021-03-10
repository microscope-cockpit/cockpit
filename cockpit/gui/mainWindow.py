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

# This module creates the primary window.  This window houses widgets
# to control the most important hardware elements.  It is only
# responsible for setting up the user interface; it assume that the
# devices have already been initialized.

import os.path
import pkg_resources
import subprocess
import sys
import typing
from itertools import chain

import wx
import wx.adv

import cockpit.gui
import cockpit.gui.fileViewerWindow
import cockpit.interfaces.channels

from cockpit import depot
from cockpit.gui.dialogs.experiment import multiSiteExperiment
from cockpit.gui.dialogs.experiment import singleSiteExperiment
from cockpit import events
import cockpit.experiment.experiment
from cockpit.gui import fileViewerWindow
from cockpit.gui import joystick
from cockpit.gui import keyboard
import cockpit.util.files
import cockpit.util.userConfig
from cockpit.gui import viewFileDropTarget
from cockpit.gui import mainPanels


ROW_SPACER = 12
COL_SPACER = 8


class MainWindowPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Find out what devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)

        ## Maps LightSource handlers to their associated panels of controls.
        self.lightToPanel = dict()

        root_sizer = wx.BoxSizer(wx.VERTICAL)

        # A row of buttons for various actions we know we can take.
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        # Abort button
        abortButton = wx.Button(self, wx.ID_ANY, "abort")
        abortButton.SetLabelMarkup("<span foreground='red'><big><b>ABORT</b></big></span>")
        abortButton.Bind(wx.EVT_BUTTON, lambda event: events.publish(events.USER_ABORT))
        buttonSizer.Add(abortButton, 1, wx.EXPAND)

        # Snap image button
        snapButton = wx.Button(self, wx.ID_ANY, "Snap\nimage")
        snapButton.Bind(wx.EVT_BUTTON, lambda evt: wx.GetApp().Imager.takeImage())
        buttonSizer.Add(snapButton, 1, wx.EXPAND)

        # Video mode button
        videoButton = wx.ToggleButton(self, wx.ID_ANY, "Live")
        videoButton.Bind(wx.EVT_TOGGLEBUTTON, lambda evt: wx.GetApp().Imager.videoMode())
        events.subscribe(cockpit.events.VIDEO_MODE_TOGGLE, lambda state: videoButton.SetValue(state))
        buttonSizer.Add(videoButton, 1, wx.EXPAND)

        # Experiment & review buttons
        for lbl, fn in ( ("Single-site\nexperiment", lambda evt: singleSiteExperiment.showDialog(self) ),
                         ("Multi-site\nexperiment", lambda evt: multiSiteExperiment.showDialog(self) ),
                         ("View last\nfile", self.onViewLastFile) ):
            btn = wx.Button(self, wx.ID_ANY, lbl)
            btn.Bind(wx.EVT_BUTTON, fn)
            buttonSizer.Add(btn, 1, wx.EXPAND)



        # Increase font size in top row buttons.
        for w in [child.GetWindow() for child in buttonSizer.Children]:
            w.SetFont(w.GetFont().Larger())
        root_sizer.Add(buttonSizer)
        root_sizer.AddSpacer(ROW_SPACER)

        # Make UIs for any other handlers / devices and insert them into
        # our window, if possible.
        # Light power things will be handled later.
        lightPowerThings = depot.getHandlersOfType(depot.LIGHT_POWER)
        lightPowerThings.sort(key = lambda l: l.wavelength)
        # Camera UIs are drawn separately. Currently, they are drawn first,
        # but this separation may make it easier to implement cameras in
        # ordered slots, giving the user control over exposure order.
        cameraThings = depot.getHandlersOfType(depot.CAMERA)
        # Ignore anything that is handled specially.
        ignoreThings = lightToggles + lightPowerThings
        ignoreThings += cameraThings
        # Remove ignoreThings from the full list of devices.
        otherThings = list(depot.getAllDevices())
        otherThings.sort(key = lambda d: d.__class__.__name__)
        otherThings.extend(depot.getAllHandlers())
        rowSizer = wx.WrapSizer(wx.HORIZONTAL)

        # Add objective control
        buttonSizer.Add(
            mainPanels.ObjectiveControls(self, wx.GetApp().Objectives),
            flag=wx.LEFT,
            border=2,
        )
        ignoreThings.extend(wx.GetApp().Objectives.GetHandlers())

        # Make the UI elements for the cameras.
        rowSizer.Add(mainPanels.CameraControlsPanel(self))
        rowSizer.AddSpacer(COL_SPACER)

        # Add light controls.
        lightfilters = sorted(depot.getHandlersOfType(depot.LIGHT_FILTER))
        ignoreThings.extend(lightfilters)

        # Add filterwheel controls.
        rowSizer.Add(mainPanels.FilterControls(self))

        # Make the UI elements for eveything else.
        for thing in ignoreThings:
            if thing in otherThings:
                otherThings.remove(thing)
        for thing in sorted(otherThings):
            if depot.getHandler(thing, depot.CAMERA):
                # Camera UIs already drawn.
                continue
            item = thing.makeUI(self)
            if item is not None:
                itemsizer = wx.BoxSizer(wx.VERTICAL)
                itemsizer.Add(cockpit.gui.mainPanels.PanelLabel(self, thing.name))
                itemsizer.Add(item, 1, wx.EXPAND)
                if rowSizer.GetChildren():
                    # Add a spacer.
                    rowSizer.AddSpacer(COL_SPACER)
                rowSizer.Add(itemsizer)

        root_sizer.Add(rowSizer, wx.SizerFlags().Expand())
        root_sizer.AddSpacer(ROW_SPACER)

        lights_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lights_sizer.Add(mainPanels.LightControlsPanel(self), flag=wx.EXPAND)
        lights_sizer.Add(mainPanels.ChannelsPanel(self), flag=wx.EXPAND)
        root_sizer.Add(lights_sizer, flag=wx.EXPAND)

        self.SetSizer(root_sizer)

        keyboard.setKeyboardHandlers(self)
        self.joystick = joystick.Joystick(self)

        self.SetDropTarget(viewFileDropTarget.ViewFileDropTarget(self))


    ## User clicked the "view last file" button; open the last experiment's
    # file in an image viewer. A bit tricky when there's multiple files
    # generated due to the splitting logic. We just view the first one in
    # that case.
    def onViewLastFile(self, event = None):
        filenames = cockpit.experiment.experiment.getLastFilenames()
        if filenames:
            window = fileViewerWindow.FileViewer(filenames[0], self)
            if len(filenames) > 1:
                print ("Opening first of %d files. Others can be viewed by dragging them from the filesystem onto the main window of the Cockpit." % len(filenames))


class EditMenu(wx.Menu):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        menu_item = self.Append(wx.ID_ANY, item="Reset User Configuration")
        self.Bind(wx.EVT_MENU, self.OnResetUserConfig, menu_item)

    def OnResetUserConfig(self, evt: wx.CommandEvent) -> None:
        cockpit.util.userConfig.clearAllValues()


class ChannelsMenu(wx.Menu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        control_items = [
            ('Add channel…', self.OnAddChannel),
            ('Remove channel…', self.OnRemoveChannel),
            ('Export channels…', self.OnExportChannels),
            ('Import channels…', self.OnImportChannels),
        ]
        for label, method in control_items:
            menu_item = self.Append(wx.ID_ANY, item=label)
            self.Bind(wx.EVT_MENU, method, menu_item)
        self.AppendSeparator()
        self._n_control_items = len(control_items) +1 # +1 for the separator
        for name in wx.GetApp().Channels.Names:
            self.AddChannelItem(name)

        wx.GetApp().Channels.Bind(cockpit.interfaces.channels.EVT_CHANNEL_ADDED,
                                  self.OnChannelAdded)
        wx.GetApp().Channels.Bind(cockpit.interfaces.channels.EVT_CHANNEL_REMOVED,
                                  self.OnChannelRemoved)


    @property
    def ChannelItems(self) -> typing.List[wx.MenuItem]:
        """List of channel items in the menu."""
        channel_items = []
        for i, menu_item in enumerate(self.MenuItems):
            if i < self._n_control_items:
                continue # skip control items
            channel_items.append(menu_item)
        return channel_items

    def AddChannelItem(self, name: str) -> None:
        menu_item = self.Append(wx.ID_ANY, item=name)
        self.Bind(wx.EVT_MENU, self.OnChannel, menu_item)

    def FindChannelItem(self, channel_name: str) -> wx.MenuItem:
        """Find the channel menu item with the given channel name."""
        # wx.Menu.FindItem works perfectly to find the channel by name
        # but we deploy our own logic to cover the case of channels
        # named like one of our control menu items.  Sure, the only
        # reason to name a channel like that is to piss us off, but we
        # still need to handle it.
        for menu_item in self.ChannelItems:
            if menu_item.ItemLabelText == channel_name:
                return menu_item
        else:
            raise ValueError('There is no menu item named \'%s\''
                             % channel_name)


    def OnChannelAdded(self, event: wx.CommandEvent) -> None:
        channel_name = event.GetString()
        self.AddChannelItem(channel_name)
        event.Skip()

    def OnChannelRemoved(self, event: wx.CommandEvent) -> None:
        channel_name = event.GetString()
        menu_item = self.FindChannelItem(channel_name)
        self.Delete(menu_item)
        event.Skip()


    def OnAddChannel(self, event: wx.CommandEvent) -> None:
        """Add current channel configuration."""
        name = wx.GetTextFromUser('Enter name for new channel:',
                                  caption='Add new channel')
        if not name:
            return

        if name in wx.GetApp().Channels.Names:
            answer = wx.MessageBox('There is already a channel named "%s".'
                                   ' Replace it?' % name,
                                   caption='Channel already exists',
                                   style=wx.YES_NO)
            if answer == wx.YES:
                channel = cockpit.interfaces.channels.CurrentChannel()
                wx.GetApp().Channels.Change(name, channel)
        else:
            channel = cockpit.interfaces.channels.CurrentChannel()
            wx.GetApp().Channels.Add(name, channel)


    def OnRemoveChannel(self, event: wx.CommandEvent) -> None:
        """Remove one channel."""
        if not wx.GetApp().Channels.Names:
            wx.MessageBox('There are no channels to be removed.',
                          caption='Failed to remove channel', style=wx.OK)
            return

        name = wx.GetSingleChoice('Choose channel to be removed:',
                                  caption='Remove a channel',
                                  aChoices=wx.GetApp().Channels.Names)
        if not name:
            return
        wx.GetApp().Channels.Remove(name)


    def OnExportChannels(self, event: wx.CommandEvent) -> None:
        """Save all channels to a file."""
        filepath = wx.SaveFileSelector('Select file to export', '')
        if not filepath:
            return
        try:
            cockpit.interfaces.channels.SaveToFile(filepath,
                                                   wx.GetApp().Channels)
        except:
            cockpit.gui.ExceptionBox('Failed to write to \'%s\'' % filepath)


    def OnImportChannels(self, event: wx.CommandEvent) -> None:
        """Add all channels in a file."""
        filepath = wx.LoadFileSelector('Select file to import', '')
        if not filepath:
            return
        try:
            new_channels = cockpit.interfaces.channels.LoadFromFile(filepath)
        except:
            cockpit.gui.ExceptionBox('Failed to read to \'%s\'' % filepath)
        current_names = wx.GetApp().Channels.Names
        duplicated = [n for n in new_channels.Names if n in current_names]
        if duplicated:
            answer = wx.MessageBox('The import will overwrite the following'
                                   ' channels: %s. Do you want to continue?'
                                   % ', '.join(duplicated),
                                   caption='Duplicated channels on loaded file',
                                   style=wx.YES_NO)
            if answer != wx.YES:
                return
        wx.GetApp().Channels.Update(new_channels)


    def OnChannel(self, event: wx.CommandEvent) -> None:
        """Apply channel with same name as the menu item."""
        name = self.FindItemById(event.GetId()).ItemLabelText
        channel = wx.GetApp().Channels.Get(name)
        cockpit.interfaces.channels.ApplyChannel(channel)


class WindowsMenu(wx.Menu):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._id_to_window = {} # type: typing.Dict[int, wx.Frame]

        menu_item = self.Append(wx.ID_ANY, item='Reset window positions')
        self.Bind(wx.EVT_MENU, self.OnResetWindowPositions, menu_item)

        # A separator between the window menu items and the other
        # extra windows.
        self.AppendSeparator()

        # Add item to launch valueLogViewer (XXX: this should be
        # handled by some sort of plugin system and not hardcoded).
        from cockpit.util import valueLogger
        from cockpit.util import csv_plotter
        menu_item = self.Append(wx.ID_ANY, "Launch ValueLogViewer")
        logs = valueLogger.ValueLogger.getLogFiles()
        if not logs:
            menu_item.Enable(False)
        else:
            shell = sys.platform == 'win32'
            args = ['python', csv_plotter.__file__] + logs
            self.Bind(wx.EVT_MENU,
                      lambda e: subprocess.Popen(args, shell=shell),
                      menu_item)

        # This is only for the piDIO and executor, both of which are a
        # window to set lines high/low.  We should probably have a
        # general window for this which we could use for all executor
        # handlers (probably piDIO device should provide an executor
        # handler).
        for obj in chain(depot.getAllHandlers(), depot.getAllDevices()):
            if hasattr(obj, 'showDebugWindow'):
                label = 'debug %s (%s)' % (obj.name, obj.__class__.__name__)
                menu_item = self.Append(wx.ID_ANY, label)
                self.Bind(wx.EVT_MENU,
                          lambda e, obj=obj: obj.showDebugWindow(),
                          menu_item)

        # When the menu is created the windows don't exist yet so we
        # will update it each time the menu is open.
        self.Bind(wx.EVT_MENU_OPEN, self.OnMenuOpen)


    def OnMenuOpen(self, event: wx.MenuEvent) -> None:
        if event.GetMenu() is not self:
            # We may be just opening one of the submenus but we only
            # want to do this when opening the main menu.
            event.Skip()
            return

        main_window = wx.GetApp().GetTopWindow()
        all_windows = {w for w in wx.GetTopLevelWindows() if w is not main_window}

        for window in all_windows.difference(self._id_to_window.values()):
            if not window.Title:
                # We have bogus top-level windows because of the use
                # of AuiManager on the logging window (see issue #617)
                # so skip windows without a title.
                continue
            menu_item = wx.MenuItem(self, wx.ID_ANY, window.Title)
            self.Bind(wx.EVT_MENU, self.OnWindowTitle, menu_item)
            self._id_to_window[menu_item.Id] = window

            # Place this menu item after the "Reset window positions"
            # but before the log viewer and debug window.
            position = len(self._id_to_window)
            self.Insert(position, menu_item)


    def OnResetWindowPositions(self, event: wx.CommandEvent) -> None:
        del event
        wx.GetApp().SetWindowPositions()


    def OnWindowTitle(self, event: wx.CommandEvent) -> None:
        """Action when user selects the menu item with the window title."""
        window = self._id_to_window[event.GetId()]
        # Don't just call Restore() without checking if the window is
        # really iconized otherwise it might unmaximize a maximized
        # window when the user only wanted to bring it to the front.
        if window.IsIconized():
            window.Restore()
        # On GTK3 calling Raise() would be enough since it also calls
        # Show(), but on other platforms we do need to call Show()
        # first (see issue #599).  It's unclear what is the expected
        # wx behaviour (see https://trac.wxwidgets.org/ticket/18762)
        window.Show()
        window.Raise()

        # On Windows and OSX, when adding/removing displays, it is
        # possible that a window is at a position that no longer
        # exists.  So ensure that the window is shown at valid
        # coordinates.
        if wx.Display.GetFromWindow(window) == wx.NOT_FOUND:
            window.SetPosition(wx.GetMousePosition())


class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Cockpit")
        panel = MainWindowPanel(self)

        menu_bar = wx.MenuBar()

        file_menu = wx.Menu()
        menu_item = file_menu.Append(wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnOpen, menu_item)
        menu_item = file_menu.Append(wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnQuit, menu_item)
        menu_bar.Append(file_menu, '&File')

        edit_menu = EditMenu()
        menu_bar.Append(edit_menu, "&Edit")

        channels_menu = ChannelsMenu()
        menu_bar.Append(channels_menu, '&Channels')

        menu_bar.Append(WindowsMenu(), '&Windows')

        help_menu = wx.Menu()
        menu_item = help_menu.Append(wx.ID_ANY, item='Online repository')
        self.Bind(wx.EVT_MENU,
                  lambda evt: wx.LaunchDefaultBrowser('https://github.com/MicronOxford/cockpit/'),
                  menu_item)
        menu_item = help_menu.Append(wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self._OnAbout, menu_item)
        menu_bar.Append(help_menu, '&Help')

        self.SetMenuBar(menu_bar)

        self.SetStatusBar(StatusLights(parent=self))

        sizer = wx.BoxSizer()
        sizer.Add(panel)
        self.SetSizerAndFit(sizer)

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Because mainPanels.PanelLabel uses a font larger than the
        # default, we need to recompute the Frame size at show time.
        # Workaround for https://trac.wxwidgets.org/ticket/16088
        if 'gtk3' in wx.PlatformInfo:
            self.Bind(wx.EVT_SHOW, self.OnShow)


    def OnShow(self, event: wx.ShowEvent) -> None:
        self.Fit()
        event.Skip()

    def OnOpen(self, event: wx.CommandEvent) -> None:
        filepath = wx.LoadFileSelector('Select file to open', '', parent=self)
        if not filepath:
            return
        try:
            cockpit.gui.fileViewerWindow.FileViewer(filepath, parent=self)
        except Exception as ex:
            cockpit.gui.ExceptionBox('Failed to open \'%s\'' % filepath,
                                     parent=self)

    def OnQuit(self, event: wx.CommandEvent) -> None:
        self.Close()

    def OnClose(self, event):
        """Close the main window, leads to close cockpit program.

        Do any necessary GUI pre-shutdown events here instead of
        CockpitApp.OnExit, since in that function all of the wx
        objects have been destroyed already.
        """
        if not event.CanVeto():
            event.Destroy()
        else:
            wx.GetApp()._SaveWindowPositions()
            # Let the default event handler handle the frame
            # destruction.
            event.Skip()

    def _OnAbout(self, event):
        wx.adv.AboutBox(CockpitAboutInfo(), parent=self)


class StatusLights(wx.StatusBar):
    """A window status bar with the Cockpit status lights.

    The status bar can have any number of status light, each status
    light being a separate field.  New lights are created on the fly
    as required by publishing `UPDATE_STATUS_LIGHT` events.  The same
    event is used to update its text.
    """
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Maps status light names to the light field/pane index.
        self._nameToField = {} # type: typing.Dict[str, int]
        self._defaultBackgroundColour = self.GetBackgroundColour()
        self._notificationColour = wx.YELLOW

        listener = cockpit.gui.EvtEmitter(self, events.UPDATE_STATUS_LIGHT)
        listener.Bind(cockpit.gui.EVT_COCKPIT, self._OnNewStatus)

        # Some lights that we know we need.
        events.publish(events.UPDATE_STATUS_LIGHT, 'image count', '')
        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting', '')


    def _AddNewLight(self, lightName: str) -> None:
        """Append new status light to the status bar."""
        new_field_index = self.GetFieldsCount() # type: int
        if not self._nameToField:
            # If the map is empty, this is the first light.  However,
            # a status bar always has at least one field, so use the
            # existing field if this is the first light.
            assert new_field_index == 1
            new_field_index = 0
        else:
            self.SetFieldsCount(new_field_index +1)
        self.SetStatusStyles([wx.SB_SUNKEN]* (new_field_index +1))
        self._nameToField[lightName] = new_field_index


    def _OnNewStatus(self, event: cockpit.gui.CockpitEvent) -> None:
        """Update text of specified status light."""
        assert len(event.EventData) == 2
        lightName = event.EventData[0] # type: str
        text = event.EventData[1] # type: str
        if lightName not in self._nameToField:
            self._AddNewLight(lightName)
        self.SetStatusText(text, self._nameToField[lightName])

        # This changes the colour of the whole bar, not only the
        # status (see issue #565).
        if any([self.GetStatusText(i) for i in range(self.FieldsCount)]):
            self.SetBackgroundColour(self._notificationColour)
        else:
            self.SetBackgroundColour(self._defaultBackgroundColour)
        # On Windows, we need to call Refresh() after
        # SetBackgroundColour() (see issue #654).
        self.Refresh()


def CockpitAboutInfo() -> wx.adv.AboutDialogInfo:
    # TODO: we should be reading all of the stuff here from somewhere
    # that is shared with setup.py.  Maybe we need our own metadata
    # class which this function would then convert.
    info = wx.adv.AboutDialogInfo()
    info.SetName('Cockpit')

    info.SetVersion(pkg_resources.get_distribution('cockpit').version)
    info.SetDescription('Hardware agnostic microscope user interface')
    info.SetCopyright('Copyright © 2020\n'
                      '\n'
                      'Cockpit comes with absolutely no warranty.\n'
                      'See the GNU General Public Licence, version 3 or later,'
                      ' for details.')

    # Authors are sorted alphabetically.
    for dev_name in ['Chris Weisiger',
                     'Danail Stoychev',
                     'David Miguel Susano Pinto',
                     'Eric Branlund',
                     'Ian Dobbie',
                     'Julio Mateos-Langerak',
                     'Mick Phillips',
                     'Nicholas Hall',
                     'Sebastian Hasse',]:
        info.AddDeveloper(dev_name)

    # wxWidgets has native and generic implementations for the about
    # dialog.  However, native implementations other than GTK are
    # limited on the info they can include.  If website, custom icon
    # (instead of inherited from the parent), and license are used on
    # platforms other than GTK the generic dialog is used which we
    # want to avoid.
    if wx.Platform == '__WXGTK__':
        info.SetWebSite('https://www.micron.ox.ac.uk/software/cockpit/')

        # We should not have to set this, it should be set later via
        # the AboutBox parent icon.  We don't yet have icons working
        # (issue #388), but remove this when it is.
        info.SetIcon(wx.Icon(os.path.join(cockpit.gui.IMAGES_PATH,
                                          'cockpit-8bit.ico')))

        info.SetLicence('Cockpit is free software: you can redistribute it'
                        ' and/or modify\nit under the terms of the GNU General'
                        ' Public License as published by\nthe Free Software'
                        ' Foundation, either version 3 of the License, or\n(at'
                        ' your option) any later version\n'
                        '\n'
                        'Cockpit is distributed in the hope that it will be'
                        ' useful,\nbut WITHOUT ANY WARRANTY; without even the'
                        ' implied warranty of\nMERCHANTABILITY or FITNESS FOR A'
                        ' PARTICULAR PURPOSE.  See the\nGNU General Public'
                        ' License for more details.\n'
                        '\n'
                        'You should have received a copy of the GNU General'
                        ' Public License\nalong with Cockpit.  If not, see '
                        ' <http://www.gnu.org/licenses/>.')
    return info


## Create the window.
def makeWindow():
    window = MainWindow()
    return window
