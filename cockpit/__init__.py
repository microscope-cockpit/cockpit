#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 Centre National de la Recherche Scientifique (CNRS)
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

import argparse
import importlib
import logging
import os
import os.path
import sys
import threading
import time
import traceback
import wx
from typing import List

import Pyro4

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
import cockpit.util.userConfig


_logger = logging.getLogger(__name__)


# Required since Pyro4 v4.22 (which is a project requirement anyway)
Pyro4.config.SERIALIZERS_ACCEPTED.discard('serpent')
Pyro4.config.SERIALIZERS_ACCEPTED.add('pickle')
Pyro4.config.SERIALIZER = 'pickle'
Pyro4.config.REQUIRE_EXPOSE = False


class CockpitApp(wx.App):
    """
    Args:
        config (:class:`cockpit.config.CockpitConfig`):
    """
    def __init__(self, config):
        ## OnInit() will make use of config, and wx.App.__init__()
        ## calls OnInit().  So we need to assign this before super().
        self._config = config
        self._depot = cockpit.depot.DeviceDepot()
        # FIXME: some places still access the depot singleton instance
        # in the module (through the module free functions) so we need
        # to keep a reference to this object there.
        cockpit.depot.deviceDepot = self._depot
        super().__init__(redirect=False)

    @property
    def Depot(self):
        return self._depot

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

    @property
    def MainWindow(self):
        return self._main_window

    def OnInit(self):
        try:
            # Ideally we would set this per device but Pyro4 config is
            # a singleton so our changes affects *all* devices we use
            # (as well as anything else on the process using Pyro).
            Pyro4.config.PICKLE_PROTOCOL_VERSION = self.Config[
                "global"
            ].getint("pyro-pickle-protocol")

            depot_config = self.Config.depot_config

            self.Depot.initialize(depot_config)

            numDevices = len(depot_config.sections()) + 1 # +1 for dummy devices
            numNonDevices = 10
            status = wx.ProgressDialog(parent = None,
                    title = "Initializing Cockpit",
                    message = "Importing modules...",
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
            for device in self.Depot.initialize(depot_config):
                status.Update(updateNum, "Initializing devices...\n%s" % device)
                updateNum+=1
            status.Update(updateNum, "Initializing device interfaces...")
            updateNum+=1

            self._imager = cockpit.interfaces.imager.Imager(
                self.Depot.getHandlersOfType(cockpit.depot.IMAGER)
            )
            cockpit.interfaces.stageMover.initialize()
            self._objectives = cockpit.interfaces.Objectives(
                self.Depot.getHandlersOfType(cockpit.depot.OBJECTIVE)
            )
            self._stage = cockpit.interfaces.stageMover.mover
            self._channels = cockpit.interfaces.channels.Channels()
            for fpath in self.Config['global'].getpaths('channel-files', []):
                new_channels = cockpit.interfaces.channels.LoadFromFile(fpath)
                self._channels.Update(new_channels)

            status.Update(updateNum, "Initializing user interface...")
            updateNum+=1

            self._main_window = cockpit.gui.mainWindow.makeWindow()
            self.SetTopWindow(self._main_window)

            # Now that the main window exists, we can reparent the
            # logging window like all the other ones.

            # We use parent.AddChild(child) even though it is not
            # recommended.  We should be using child.Reparent(parent)
            # but that fails pretty bad in wxMSW and wxOSX (see issue
            # #618 and https://trac.wxwidgets.org/ticket/18785)
            self._main_window.AddChild(logging_window)

            for module_name in ['cockpit.gui.camera.window',
                                'cockpit.gui.mosaic.window',
                                'cockpit.gui.macroStage.macroStageWindow',
                                'cockpit.gui.shellWindow',
                                'cockpit.gui.touchscreen']:
                module = importlib.import_module(module_name)
                status.Update(updateNum, ' ... ' + module_name)
                updateNum += 1
                module.makeWindow(self._main_window)

            self.SetWindowPositions()

            self._main_window.Show()
            for window in wx.GetTopLevelWindows():
                if window is self._main_window:
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

            self.Depot.makeInitialPublications()
            cockpit.interfaces.stageMover.makeInitialPublications()

            cockpit.events.publish(cockpit.events.COCKPIT_INIT_COMPLETE)
            self.Bind(wx.EVT_ACTIVATE_APP, self.onActivateApp)
            return True
        except Exception as e:
            cockpit.gui.ExceptionBox(caption='Failed to initialise cockpit')
            _logger.error("Initialization failed: %s" % e)
            _logger.error(traceback.format_exc())
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
            _logger.error("Error on USER_ABORT during exit")
            _logger.error(traceback.format_exc())
        for dev in self.Depot.getAllDevices():
            try:
                dev.onExit()
            except:
                _logger.error("Error on device '%s' during exit", dev.name)
                _logger.error(traceback.format_exc())
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
            title=window.GetTitle()
            #camera views title can need to be stripped.
            if title.startswith('Camera views '):
                title='Camera views'
            config_name = 'Show Window ' + title
            cockpit.util.userConfig.setValue(config_name, window.IsShown())


def show_exception_app() -> None:
    app = wx.App()
    cockpit.gui.ExceptionBox(caption='Failed to initialise cockpit')
    ## We ProcessPendingEvents() instead of entering the MainLoop()
    ## because we won't have more windows created, meaning that the
    ## program would not exit after closing the exception box.
    app.ProcessPendingEvents()


def _parse_cmd_line_args(cmd_line_args: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cockpit")

    parser.add_argument(
        "--config-file",
        dest="config_files",
        action="append",
        default=[],
        metavar="COCKPIT-CONFIG-PATH",
        help="File path for another cockpit config file",
    )
    parser.add_argument(
        "--no-user-config-files",
        dest="read_user_config_files",
        action="store_false",
        help="Do not read user config files"
    )
    parser.add_argument(
        "--no-system-config-files",
        dest="read_system_config_files",
        action="store_false",
        help="Do not read system config files"
    )
    parser.add_argument(
        "--no-config-files",
        dest="read_config_files",
        action="store_false",
        help="Do not read user and system config files"
    )

    parser.add_argument(
        "--depot-file",
        dest="depot_files",
        action="append",
        default=[],
        metavar="DEPOT-CONFIG-PATH",
        help="File path for depot device configuration"
    )

    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging level"
    )

    cmd_line_options = parser.parse_args(cmd_line_args[1:])

    ## '--no-config-files' is just a convenience flag option for
    ## '--no-user-config-file --no-system-config-files'
    if not cmd_line_options.read_config_files:
        cmd_line_options.read_user_config_files = False
        cmd_line_options.read_system_config_files = False

    return cmd_line_options


def _configure_logging(config) -> None:
    """Setup the *root* logger.

    Args:
        logging_config (``configparser.SectionProxy``): the config
            section for the logger.
    """
    log_dir = config.getpath('dir')
    os.makedirs(log_dir, exist_ok=True)

    filename = time.strftime(config.get('filename-template'))
    filepath = os.path.join(log_dir, filename)

    level = getattr(logging, config.get('level').upper())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    log_handler = logging.FileHandler(filepath, mode = "a")
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s'
                                  + ' %(module)10s:%(lineno)4d'
                                  + '  %(message)s')
    log_handler.setFormatter(formatter)
    log_handler.setLevel(level)
    root_logger.addHandler(log_handler)


def _pre_gui_init(argv: List[str]) -> cockpit.config.CockpitConfig:
    """Cockpit initialisation before we have a GUI."""
    ## Logging setup has four phases:
    ##
    ##   1) an initial configuration with Python's default so we can
    ##      have logs from the very beginning even if only on the
    ##      command line;
    ##   2) after parsing the command line options, maybe change the
    ##      logging level if there is --debug flag;
    ##   3) after we have read and parse all configuration files,
    ##      logging starts properly possibly written to a file (in
    ##      addition to the command line);
    ##   4) once the CockpitApp have started, logs are also displayed
    ##      on Cockpit's logging window.

    logging.basicConfig()
    cmd_line_options = _parse_cmd_line_args(argv)
    if cmd_line_options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    config = cockpit.config.CockpitConfig(cmd_line_options)
    _configure_logging(config['log'])

    data_dir = config.getpath('global', 'data-dir')
    _logger.info("Creating data-dir '%s' if needed", data_dir)
    os.makedirs(data_dir, exist_ok=True)

    return config


def main(argv: List[str]) -> int:
    try:
        config = _pre_gui_init(argv)
    ## If anything happens during this initial stage there is no UI
    ## yet, so create a simple UI to display the exception text.
    ## Then, re-raise the caught exception so that it is displayed on
    ## command line and for whatever cleanup Python does.
    except SystemExit as ex:
        ## Do not show exception UI on exit code zero because it was
        ## not an error, maybe 'cockpit --help' was called.
        if ex.code != 0:
            show_exception_app()
        raise ex
    except BaseException as ex:
        show_exception_app()
        raise ex

    app = CockpitApp(config=config)
    app.MainLoop()

    # HACK: manually exit the program if we find threads running.  At
    # this point, any thread running is non-daemonic, i.e., a thread
    # that doesn't exit when the main thread exits.  These will make
    # cockpit process hang and require it to be manually terminated.
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
        _logger.error(
            "Found %d non-daemon threads at exit.  These are:", len(badThreads)
        )
        for thread in badThreads:
            _logger.error("Thread '%s': %s", thread.name, thread.__dict__)
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
