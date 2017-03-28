#!/usr/bin/env python
## This module is the base module for running the cockpit software; invoke
# Python on it to start the program. It initializes everything and creates
# the GUI.

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

# We need these first to ensure that we can log failures during startup.
import depot
depot.loadConfig()
import util.files
import util.logger
util.files.initialize()
util.files.ensureDirectoriesExist()
util.logger.makeLogger()

COCKPIT_PATH = os.path.dirname(os.path.abspath(__file__))

class CockpitApp(wx.App):
    def OnInit(self):
        try:
            # Allow subsequent actions to abort startup by publishing
            # a "program startup failure" event.
            import events
            events.subscribe('program startup failure', self.onStartupFail)
            events.subscribe('program exit', self.onExit)
            
            # If I don't import util here, then if initialization fails
            # due to one of the other imports, Python complains about
            # local variable 'util' being used before its assignment,
            # because of the "import util.user" line further down combined
            # with the fact that we want to use util.logger to log the
            # initialization failure. So instead we have a useless
            # import to ensure we can access the already-loaded util.logger.
            import util
            import depot

            status = wx.ProgressDialog(parent = None,
                    title = "Initializing OMX Cockpit",
                    message = "Importing modules...",
                    maximum = 5 + depot.getNumModules())
            status.Show()
            
            import gui.camera.window
            import gui.loggingWindow
            # Do this early so we can see output while initializing.
            gui.loggingWindow.makeWindow(None)
            import gui.macroStage.macroStageWindow
            import gui.mainWindow
            import gui.mosaic.window
            import gui.shellWindow
            import gui.statusLightsWindow
            import interfaces
            import util.user
            import util.userConfig

            updateNum=1
            status.Update(updateNum, "Initializing config...")
            updateNum+=1
            util.userConfig.initialize()

            status.Update(updateNum, "Initializing devices...")
            updateNum+=1
            for i, module in enumerate(depot.initialize()):
                status.Update(updateNum, "Initializing devices...\n%s" % module)
                updateNum+=1
            status.Update(updateNum, "Initializing device interfaces...")
            updateNum+=1
            interfaces.initialize()

            status.Update(updateNum, "Initializing user interface...")
            updateNum+=1
                            
            frame = gui.mainWindow.makeWindow()
            status.Update(updateNum, " ... camera window")
            updateNum+=1
            self.SetTopWindow(frame)
            gui.camera.window.makeWindow(frame)
            status.Update(updateNum, " ... mosaic window")
            updateNum+=1
            gui.mosaic.window.makeWindow(frame)
            status.Update(updateNum, " ... macrostage window")
            updateNum+=1
            gui.macroStage.macroStageWindow.makeWindow(frame)
            status.Update(updateNum, " ... shell window")
            updateNum+=1
            gui.shellWindow.makeWindow(frame)
            status.Update(updateNum, " ... statuslights window")
            updateNum+=1
            gui.statusLightsWindow.makeWindow(frame)

            # At this point, we have all the main windows are displayed.
            self.primaryWindows = [w for w in wx.GetTopLevelWindows()]
            # Now create secondary windows. These are single instance
            # windows that won't appear in the primary window marshalling
            # list.
            status.Update(updateNum, " ... secondary windows")
            updateNum+=1

            import gui.valueLogger
            gui.valueLogger.makeWindow(frame)
            from util import intensity
            intensity.makeWindow(frame)
            # All secondary windows created.
            self.secondaryWindows = [w for w in wx.GetTopLevelWindows() if w not in self.primaryWindows]

            for w in self.secondaryWindows:
                #bind close event to just hide for these windows
                w.Bind(wx.EVT_CLOSE, lambda event: w.Hide())
            
            # Now that the UI exists, we don't need this any more.
        	# Sometimes, status doesn't make it into the list, so test.
            if status in self.primaryWindows:
                self.primaryWindows.remove(status)
            status.Destroy()

            util.user.login(frame)
            util.logger.log.debug("Login complete as %s", util.user.getUsername())

            #now loop over secondary windows open and closeing as needed.
            for w in self.secondaryWindows:
                # get saved state of secondary windows.
                title=w.GetTitle()
                windowstate=util.userConfig.getValue('windowState'+title,
                                                isGlobal = False,
                                                default= 0)
                #if they were hidden then return them to hidden
                if (windowstate is 0): 
                    # Hide the window until it is called up.
                    w.Hide()
                
            
            depot.makeInitialPublications()
            interfaces.makeInitialPublications()
            events.publish('cockpit initialization complete')
            self.Bind(wx.EVT_ACTIVATE_APP, self.onActivateApp)
            return True
        except Exception as e:
            wx.MessageDialog(None,
                    "An error occurred during initialization:\n\n" +
                    ("%s\n\n" % e) +
                    "A full code traceback follows:\n\n" +
                    traceback.format_exc() +
                    "\nThere may be more details in the logs.").ShowModal()
            util.logger.log.error("Initialization failed: %s" % e)
            util.logger.log.error(traceback.format_exc())
            return False

    def onActivateApp(self, event):
        if not event.Active:
            return
        top = wx.GetApp().GetTopWindow()
        windows = top.GetChildren()
        for w in windows:
            if w.IsShown(): w.Raise()
        top.Raise()

    ## Startup failed; log the failure information and exit.
    def onStartupFail(self, *args):
        util.logger.log.error("Startup failed: %s" % args)
        sys.exit()


    # Do anything we need to do to shut down cleanly. At this point UI
    # objects still exist, but they won't by the time we're done.
    def onExit(self):
        import util.user
        util.user.logout(shouldLoginAgain = False)
        # Manually clear out any parent-less windows that still exist. This
        # can catch some windows that are spawned by WX and then abandoned,
        # typically because of bugs in the program. If we don't do this, then
        # sometimes the program will continue running, invisibly, and must
        # be killed via Task Manager. 
        for window in wx.GetTopLevelWindows():
            util.logger.log.error("Destroying %s" % window)
            window.Destroy()

        # Call any deviec onExit code to, for example, close shutters and
        # switch of lasers.
        for dev in depot.getAllDevices():
            try:
                dev.onExit()
            except:
                pass



if __name__ == '__main__':
    CockpitApp(redirect = False).MainLoop()
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
        util.logger.log.error("Still have non-daemon threads %s" % map(str, badThreads))
        for thread in badThreads:
            util.logger.log.error(str(thread.__dict__))
    os._exit(0)

