#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018-2019 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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


## This module is the base module for running the cockpit software; invoke
# Python on it to start the program. It initializes everything and creates
# the GUI.

import importlib
import os
import sys
import threading
import traceback
import typing
import wx

import Pyro4
import distutils.version
if (distutils.version.LooseVersion(Pyro4.__version__) >=
    distutils.version.LooseVersion('4.22')):
    Pyro4.config.SERIALIZERS_ACCEPTED.discard('serpent')
    Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')
    Pyro4.config.SERIALIZER = 'pickle'
    Pyro4.config.REQUIRE_EXPOSE = False

import cockpit.config
import cockpit.depot
import cockpit.events
import cockpit.gui
import cockpit.gui.loggingWindow
import cockpit.gui.mainWindow
import cockpit.interfaces
import cockpit.interfaces.channels
import cockpit.interfaces.imager
import cockpit.interfaces.stageMover
import cockpit.util.files
import cockpit.util.logger
import cockpit.util.userConfig


class CockpitApp(wx.App):
    """
    Args:
        config (:class:`cockpit.config.CockpitConfig`):
    """
    def __init__(self, config):
        ## OnInit() will make use of config, and wx.App.__init__()
        ## calls OnInit().  So we need to assign this before super().
        self._config = config
        super().__init__(redirect=False)

    @property
    def Config(self):
        return self._config

    @property
    def Channels(self):
        return self._channels

    @property
    def Imager(self):
        return self._imager

    @property
    def Objectives(self):
        return self._objectives

    @property
    def Stage(self):
        return self._stage

    def OnInit(self):
        try:
            # Ideally we would set this per device but Pyro4 config is
            # a singleton so our changes affects *all* devices we use
            # (as well as anything else on the process using Pyro).
            Pyro4.config.PICKLE_PROTOCOL_VERSION = self.Config[
                "global"
            ].getint("pyro-pickle-protocol")
            depot_config = self.Config.depot_config
            cockpit.depot.initialize(depot_config)
            numDevices = len(depot_config.sections()) + 1 # +1 for dummy devices
            numNonDevices = 15
            status = wx.ProgressDialog(parent = None,
                    title = "Initializing OMX Cockpit",
                    message = "Importing modules...",
                    ## Fix maximum: + 1 is for dummy devices
                    maximum = numDevices + numNonDevices)
            status.Show()

            # Do this early so we can see output while initializing.
            logging_window = cockpit.gui.loggingWindow.makeWindow(None)

            updateNum=1
            status.Update(updateNum, "Initializing config...")
            updateNum+=1
            cockpit.util.userConfig.initialize(self.Config)

            status.Update(updateNum, "Initializing devices...")
            updateNum+=1
            for device in cockpit.depot.initialize(depot_config):
                status.Update(updateNum, "Initializing devices...\n%s" % device)
                updateNum+=1
            status.Update(updateNum, "Initializing device interfaces...")
            updateNum+=1

            self._imager = cockpit.interfaces.imager.Imager(
                cockpit.depot.getHandlersOfType(cockpit.depot.IMAGER)
            )
            cockpit.interfaces.stageMover.initialize()
            self._objectives = cockpit.interfaces.Objectives(
                cockpit.depot.getHandlersOfType(cockpit.depot.OBJECTIVE)
            )
            self._stage = cockpit.interfaces.stageMover.mover
            self._channels = cockpit.interfaces.channels.Channels()
            for fpath in self.Config['global'].getpaths('channel-files', []):
                new_channels = cockpit.interfaces.channels.LoadFromFile(fpath)
                self._channels.Update(new_channels)

            status.Update(updateNum, "Initializing user interface...")
            updateNum+=1

            main_window = cockpit.gui.mainWindow.makeWindow()
            self.SetTopWindow(main_window)

            # Now that the main window exists, we can reparent the
            # logging window like all the other ones.

            # We use parent.AddChild(child) even though it is not
            # recommended.  We should be using child.Reparent(parent)
            # but that fails pretty bad in wxMSW and wxOSX (see issue
            # #618 and https://trac.wxwidgets.org/ticket/18785)
            main_window.AddChild(logging_window)

            for module_name in ['cockpit.gui.camera.window',
                                'cockpit.gui.mosaic.window',
                                'cockpit.gui.macroStage.macroStageWindow',
                                'cockpit.gui.shellWindow',
                                'cockpit.gui.touchscreen',
                                'cockpit.util.intensity']:
                module = importlib.import_module(module_name)
                status.Update(updateNum, ' ... ' + module_name)
                updateNum += 1
                module.makeWindow(main_window)

            self.SetWindowPositions()

            main_window.Show()
            for window in wx.GetTopLevelWindows():
                if window is main_window:
                    continue
                # Cockpit assumes we have window singleton, so bind
                # close event to hide them.
                window.Bind(wx.EVT_CLOSE, lambda event, w=window: w.Hide())
                # Show/Hide windows at start is decided with:
                #   1. check userConfig (value from last time)
                #   2. check window class property SHOW_DEFAULT
                #   3. if none of the above is set, hide
                default_show = getattr(window, 'SHOW_DEFAULT', False)
                config_name = 'Show Window ' + window.GetTitle()
                to_show = cockpit.util.userConfig.getValue(config_name,
                                                           default=default_show)
                window.Show(to_show)

            # Now that the UI exists, we don't need this any more.
            # Sometimes, status doesn't make it into the list, so test.
            status.Destroy()

            cockpit.depot.makeInitialPublications()
            cockpit.interfaces.stageMover.makeInitialPublications()

            cockpit.events.publish('cockpit initialization complete')
            self.Bind(wx.EVT_ACTIVATE_APP, self.onActivateApp)
            return True
        except Exception as e:
            cockpit.gui.ExceptionBox(caption='Failed to initialise cockpit')
            cockpit.util.logger.log.error("Initialization failed: %s" % e)
            cockpit.util.logger.log.error(traceback.format_exc())
            return False

    def onActivateApp(self, event):
        # If we move to another app then back to cockpit, only MainWindow is
        # raised - our other windows can remain hidden by the other app, so
        # we need to raise all our top-level windows.
        if not event.Active:
            return

        top = wx.GetApp().GetTopWindow()
        # wx.Choice controls cause emission of wxEVT_ACTIVATE_APP events for
        # some reason. We don't want to re-raise windows just because the user
        # clicked a wx.Choice. The only way I can find to discriminate these
        # events from those we want to respond to is to look at top.FindFocus().
        # This returns None if the event is a result of using a wx.Choice, or
        # a reference to a control or window otherwise.
        focussed = top.FindFocus()
        if focussed is None:
            return
        for w in top.GetChildren():
            if isinstance(w, wx.TopLevelWindow) and w.IsShown():
                w.Raise()
        uppermost = focussed.GetTopLevelParent()
        # Ensure focussed item's window is at top of Z-stack.
        uppermost.Raise()
        # Ensure main window is raised.
        if top is not uppermost:
            top.Raise()

    def OnExit(self) -> int:
        """Do any non-GUI cleanup.

        At this point, all windows and controls have been removed, and
        wx has ran its cleanup next.  This is the moment to cleanup
        all our non wx stuff.

        """
        try:
            cockpit.events.publish(cockpit.events.USER_ABORT)
        except:
            cockpit.util.logger.log.error("Error on USER_ABORT during exit")
            cockpit.util.logger.log.error(traceback.format_exc())
        for dev in cockpit.depot.getAllDevices():
            try:
                dev.onExit()
            except:
                cockpit.util.logger.log.error(
                    "Error on device '%s' during exit", dev.name
                )
                cockpit.util.logger.log.error(traceback.format_exc())
        # Documentation states that we must return the same return value
        # as the base class.
        return super().OnExit()


    def SetWindowPositions(self):
        """Place the windows in the position defined in userConfig.

        This should probably be a private method, or at least a method
        that would take the positions dict as argument.
        """
        positions = cockpit.util.userConfig.getValue('WindowPositions',
                                                     default={})
        for window in wx.GetTopLevelWindows():
            if window.Title not in positions:
                continue

            # Saved window position may be invalid if, for example,
            # displays have been removed, so check it before trying to
            # move the window (see #730).
            position = positions[window.Title]
            if wx.Display.GetFromPoint(position) != wx.NOT_FOUND:
                window.SetPosition(position)


    def _SaveWindowPositions(self):
        positions = {w.Title : tuple(w.Position)
                     for w in wx.GetTopLevelWindows()}

        ## XXX: the camera window uses the title to include pixel info
        ## so fix the title so we can use it as ID later.
        camera_window_title = None
        for title in positions.keys():
            if title.startswith('Camera views '):
                camera_window_title = title
                break
        if camera_window_title is not None:
            positions['Camera views'] = positions.pop(camera_window_title)

        cockpit.util.userConfig.setValue('WindowPositions', positions)

        for window in wx.GetTopLevelWindows():
            if window is wx.GetApp().GetTopWindow():
                continue
            config_name = 'Show Window ' + window.GetTitle()
            cockpit.util.userConfig.setValue(config_name, window.IsShown())


def main(argv: typing.Sequence[str]) -> int:
    ## wxglcanvas (used in the mosaic windows) does not work with
    ## wayland (see https://trac.wxwidgets.org/ticket/17702).  The
    ## workaround is to force GTK to use the x11 backend.  See also
    ## cockpit issue #347
    if wx.Platform == '__WXGTK__' and 'GDK_BACKEND' not in os.environ:
        os.environ['GDK_BACKEND'] = 'x11'

    try:
        config = cockpit.config.CockpitConfig(argv)
        cockpit.util.logger.makeLogger(config['log'])
        cockpit.util.files.initialize(config)
    except:
        app = wx.App()
        cockpit.gui.ExceptionBox(caption='Failed to initialise cockpit')
        # We ProcessPendingEvents() instead of entering the MainLoop()
        # because we won't have more windows created, meaning that the
        # program would not exit after closing the exception box.
        app.ProcessPendingEvents()
    else:
        app = CockpitApp(config=config)
        app.MainLoop()

    # HACK: manually exit the program if we find threads running.  At
    # this point, any thread running is non-daemonic, i.e., a thread
    # that doesn't exit when the main thread exits.  These will make
    # cockipt process hang and require it to be manually terminated.
    # Why do we have non-daemonic threads?  Daemon status is inherited
    # from the parent thread, and must be manually set.  Since it is
    # easy to forget, we'll leave this here to catch any failure and
    # remind us.
    #
    # All this assumes that cockpit is the only program running and this
    # prevents `cockpit.main()` from being called in other programs.
    badThreads = []
    for thread in threading.enumerate():
        if not thread.daemon and thread is not threading.main_thread():
            badThreads.append(thread)
    if badThreads:
        cockpit.util.logger.log.error(
            "Found %d non-daemon threads at exit.  These are:", len(badThreads)
        )
        for thread in badThreads:
            cockpit.util.logger.log.error(
                "Thread '%s': %s", thread.name, thread.__dict__
            )
        os._exit(1)
    return 0


def _setuptools_entry_point() -> int:
    # The setuptools entry point must be a function, it can't be a
    # module or a package.  Also, setuptools does not pass sys.argv to
    # the entry option, the entry point must access sys.argv itself
    # but we want our main to take argv as argument so it can be
    # called from other programs.  We also don't want main's argv
    # argument to default to sys.argv because 1) bad idea to use
    # mutable objects as default arguments, and 2) when the
    # documentation is generated (with Sphinx's autodoc extension),
    # then sys.argv gets replaced with the sys.argv value at the time
    # docs were generated (see https://stackoverflow.com/a/12087750 ).
    return main(sys.argv)
