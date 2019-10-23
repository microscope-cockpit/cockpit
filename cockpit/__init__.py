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
        super(CockpitApp, self).__init__(redirect=False)

    @property
    def Config(self):
        return self._config

    def OnInit(self):
        try:
            # Allow subsequent actions to abort startup by publishing
            # a "program startup failure" event.
            events.subscribe('program startup failure', self.onStartupFail)
            events.subscribe('program exit', self.onExit)

            depot_config = self.Config.depot_config
            depot.initialize(depot_config)
            numDevices = len(depot_config.sections()) + 1 # + 1 is for dummy devs.
            numNonDevices = 15
            status = wx.ProgressDialog(parent = None,
                    title = "Initializing OMX Cockpit",
                    message = "Importing modules...",
                    ## Fix maximum: + 1 is for dummy devices
                    maximum = numDevices + numNonDevices)
            status.Show()

            # Do this early so we can see output while initializing.
            from cockpit.gui import loggingWindow
            loggingWindow.makeWindow(None)

            updateNum=1
            status.Update(updateNum, "Initializing config...")
            updateNum+=1
            cockpit.util.userConfig.initialize(self.Config)

            status.Update(updateNum, "Initializing devices...")
            updateNum+=1
            for i, device in enumerate(depot.initialize(depot_config)):
                status.Update(updateNum, "Initializing devices...\n%s" % device)
                updateNum+=1
            status.Update(updateNum, "Initializing device interfaces...")
            updateNum+=1
            cockpit.interfaces.imager.initialize()
            cockpit.interfaces.stageMover.initialize()

            status.Update(updateNum, "Initializing user interface...")
            updateNum+=1

            from cockpit.gui import mainWindow
            frame = mainWindow.makeWindow()
            self.SetTopWindow(frame)

            for subname in ['camera.window',
                            'mosaic.window',
                            'macroStage.macroStageWindow',
                            'statusLightsWindow']:
                module = importlib.import_module('cockpit.gui.' + subname)
                status.Update(updateNum, ' ... ' + subname)
                updateNum+=1
                module.makeWindow(frame)
            # At this point, we have all the main windows are displayed.
            self.primaryWindows = [w for w in wx.GetTopLevelWindows()]

            # Now create secondary windows. These are single instance
            # windows that won't appear in the primary window marshalling
            # list.
            status.Update(updateNum, " ... secondary windows")
            updateNum+=1
            for module_name in ['cockpit.gui.shellWindow',
                                'cockpit.gui.touchscreen',
                                'cockpit.util.intensity']:
                module = importlib.import_module(module_name)
                module.makeWindow(frame)

            # All secondary windows created.
            self.secondaryWindows = [w for w in wx.GetTopLevelWindows() if w not in self.primaryWindows]

            for w in self.secondaryWindows:
                #bind close event to just hide for these windows
                w.Bind(wx.EVT_CLOSE, lambda event, w=w: w.Hide())
                # get saved state of secondary windows.
                title=w.GetTitle()
                windowstate=cockpit.util.userConfig.getValue(
                                                'windowState'+title,
                                                default= 0)
                #if they were hidden then return them to hidden
                if (windowstate is 0):
                    # Hide the window until it is called up.
                    w.Hide()

            # Now that the UI exists, we don't need this any more.
            # Sometimes, status doesn't make it into the list, so test.
            if status in self.primaryWindows:
                self.primaryWindows.remove(status)
            status.Destroy()

            self.SetWindowPositions()

            #now loop over secondary windows open and closeing as needed.
            for w in self.secondaryWindows:
                # get saved state of secondary windows.
                title=w.GetTitle()
                windowstate=cockpit.util.userConfig.getValue(
                                                'windowState'+title,
                                                default= 0)
                #if they were hidden then return them to hidden
                if (windowstate is 0):
                    # Hide the window until it is called up.
                    w.Hide()


            cockpit.depot.makeInitialPublications()
            cockpit.interfaces.imager.makeInitialPublications()
            cockpit.interfaces.stageMover.makeInitialPublications()

            events.publish('cockpit initialization complete')
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

    ## Startup failed; log the failure information and exit.
    def onStartupFail(self, *args):
        cockpit.util.logger.log.error("Startup failed: %s" % args)
        sys.exit()


    # Do anything we need to do to shut down cleanly. At this point UI
    # objects still exist, but they won't by the time we're done.
    def onExit(self):
        self._SaveWindowPositions()

        try:
            events.publish("user abort")
        except Exception as e:
            cockpit.util.logger.log.error("Error during logout: %s" % e)
            cockpit.util.logger.log.error(traceback.format_exc())

        import cockpit.gui.loggingWindow
        cockpit.gui.loggingWindow.window.WriteToLogger(cockpit.util.logger.log)

        # Manually clear out any parent-less windows that still exist. This
        # can catch some windows that are spawned by WX and then abandoned,
        # typically because of bugs in the program. If we don't do this, then
        # sometimes the program will continue running, invisibly, and must
        # be killed via Task Manager.
        for window in wx.GetTopLevelWindows():
            cockpit.util.logger.log.error("Destroying %s" % window)
            window.Destroy()

        # Call any deviec onExit code to, for example, close shutters and
        # switch of lasers.
        for dev in cockpit.depot.getAllDevices():
            try:
                dev.onExit()
            except:
                pass
        # The following cleanup code used to be in main(), after App.MainLoop(),
        # where it was never reached.
        # HACK: manually exit the program. If we don't do this, then there's a small
        # possibility that non-daemonic threads (i.e. ones that don't exit when the
        # main thread exits) will hang around uselessly, forcing the program to be
        # manually shut down via Task Manager or equivalent. Why do we have non-daemonic
        # threads? That's tricky to track down. Daemon status is inherited from the
        # parent thread, and must be manually set otherwise. Since it's easy to get
        # wrong, we'll just leave this here to catch any failures to set daemon
        # status.
        badThreads = []
        for thread in threading.enumerate():
            if not thread.daemon:
                badThreads.append(thread)
        if badThreads:
            cockpit.util.logger.log.error("Still have non-daemon threads %s" % map(str, badThreads))
            for thread in badThreads:
                cockpit.util.logger.log.error(str(thread.__dict__))
        os._exit(0)


    def SetWindowPositions(self):
        """Place the windows in the position defined in userConfig.

        This should probably be a private method, or at least a method
        that would take the positions dict as argument.
        """
        positions = cockpit.util.userConfig.getValue('WindowPositions',
                                                     default={})
        for window in wx.GetTopLevelWindows():
            if window.Title in positions:
                window.SetPosition(positions[window.Title])


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


def main():
    ## wxglcanvas (used in the mosaic windows) does not work with
    ## wayland (see https://trac.wxwidgets.org/ticket/17702).  The
    ## workaround is to force GTK to use the x11 backend.  See also
    ## cockpit issue #347
    if wx.Platform == '__WXGTK__' and 'GDK_BACKEND' not in os.environ:
        os.environ['GDK_BACKEND'] = 'x11'

    ## TODO: have this in a try, and show a window (would probably
    ## need to be different wx.App), with the error if it fails.
    config = cockpit.config.CockpitConfig(sys.argv)
    cockpit.util.logger.makeLogger(config['log'])
    cockpit.util.files.initialize(config)

    app = CockpitApp(config=config)
    app.MainLoop()


if __name__ == '__main__':
    main()
