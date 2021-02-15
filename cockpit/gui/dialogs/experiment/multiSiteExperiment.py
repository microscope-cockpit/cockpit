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


import time
import wx

from cockpit import depot
from cockpit import events
import cockpit.gui.dialogs.enumerateSitesPanel
from cockpit.gui import guiUtils
from cockpit.gui.dialogs.experiment import experimentConfigPanel
import cockpit.interfaces.stageMover
import cockpit.util.userConfig
import cockpit.util.threads

## Minimum size of controls (counting their labels)
CONTROL_SIZE = (280, -1)
## Minimum size of text input fields.
FIELD_SIZE = (70, -1)

_FILENAME_TEMPLATE = "{date}-{time}_t{cycle}_p{site}.mrc"


## This class allows for configuring multi-site experiments.
class MultiSiteExperimentDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent,
                title = "OMX multi-site experiment",
                style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        ## Whether or not we should abort the current experiment.
        self.shouldAbort = False
        events.subscribe(events.USER_ABORT, self.onAbort)
        
        ## List of all light handlers.
        self.allLights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        ## List of booleans indicating which lights were active at the
        # start of the experiment.
        self.activeLights = [None for l in self.allLights]

        ## User's last-used inputs.
        self.settings = cockpit.util.userConfig.getValue('multiSiteExperiment',
                default = {
                    'numCycles': '10',
                    'cycleDuration': '60',
                    'delayBeforeStarting': '0',
                    'delayBeforeImaging': '0',
                    'fileBase': '',
                    'shouldCustomizeLightFrequencies': False,
                    'shouldOptimizeSiteOrder': True,
                    'lightFrequencies': ['1' for l in self.allLights],
                }
        )

        ## Contains self.panel
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        ## Contains all UI widgets.
        self.panel = wx.Panel(self)
        ## Sizer for self.panel.
        self.panelSizer = wx.BoxSizer(wx.VERTICAL)
        ## Sizer for all controls except the start/cancel/reset buttons.
        controlsSizer = wx.BoxSizer(wx.HORIZONTAL)
        ## Sizer for a single column of controls.
        columnSizer = wx.BoxSizer(wx.VERTICAL)
        ## Panel for selecting sites to visit.
        self.sitesPanel = cockpit.gui.dialogs.enumerateSitesPanel.EnumerateSitesPanel(
                self.panel, label = "Sites to visit:",
                size = (200, -1), minSize = CONTROL_SIZE)
        columnSizer.Add(self.sitesPanel)

        self.numCycles = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Number of cycles:",
                defaultValue = self.settings['numCycles'],
                size = FIELD_SIZE, minSize = CONTROL_SIZE)

        self.cycleDuration = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Min cycle duration (s):",
                defaultValue = self.settings['cycleDuration'],
                size = FIELD_SIZE, minSize = CONTROL_SIZE,
                helperString =
                "Minimum amount of time to pass between each cycle. If the " +
                "cycle finishes early, then I will wait until this much " +
                "time has passed. You can enter multiple values here " +
                "separated by commas; I will then use each wait time in " +
                "sequence; e.g. \"60,120,180\" means the first " +
                "cycle takes one minute, the second two, the third three, " +
                "the fourth one, the fifth two, and so on.")

        self.delayBeforeStarting = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Delay before starting (min):",
                defaultValue = self.settings['delayBeforeStarting'],
                size = FIELD_SIZE, minSize = CONTROL_SIZE,
                helperString =
                "Amount of time to wait before starting the experiment. " + 
                "This is useful if you have a lengthy period to wait for " +
                "your cells to reach the stage you're interested in, for " + 
                "example.")

        self.delayBeforeImaging = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Delay before imaging (s):",
                defaultValue = self.settings['delayBeforeImaging'],
                size = FIELD_SIZE, minSize = CONTROL_SIZE,
                helperString =
                "Amount of time to wait after moving to a site before " +
                "I start imaging the site. This is mostly useful if " +
                "your stage needs time to stabilize after moving.")

        self.fileBase = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Data file base name:",
                defaultValue = self.settings['fileBase'],
                size = FIELD_SIZE, minSize = CONTROL_SIZE)
        
        controlsSizer.Add(columnSizer, 0, wx.ALL, 5)

        columnSizer = wx.BoxSizer(wx.VERTICAL)
        ## We don't necessarily have this option.
        self.shouldPowerDownWhenDone = None
        powerHandlers = depot.getHandlersOfType(depot.POWER_CONTROL)
        if powerHandlers:
            # There are devices that we could potentially turn off at end of
            # experiment.
            self.shouldPowerDownWhenDone = guiUtils.addLabeledInput(
                    self.panel, columnSizer,
                    label = "Power off devices when done:",
                    control = wx.CheckBox(self.panel),
                    labelHeightAdjustment = 0, border = 3, flags = wx.ALL,
                    helperString =
                    "If checked, then at the end of the experiment, I will " +
                    "power down all the devices I can.")
                
        self.shouldOptimizeSiteOrder = guiUtils.addLabeledInput(self.panel,
                columnSizer, label = "Optimize route:",
                defaultValue = self.settings['shouldOptimizeSiteOrder'],
                control = wx.CheckBox(self.panel),
                labelHeightAdjustment = 0, border = 3, flags = wx.ALL,
                helperString =
                "If checked, then I will calculate an ordering of the sites " +
                "that will minimize the total time spent in transit; " +
                "otherwise, I will use the order you specify.")

        self.shouldCustomizeLightFrequencies = guiUtils.addLabeledInput(
                self.panel, columnSizer, label = "Customize light frequencies:",
                defaultValue = self.settings['shouldCustomizeLightFrequencies'],
                control = wx.CheckBox(self.panel),
                labelHeightAdjustment = 0, border = 3, flags = wx.ALL,
                helperString = 
                "This allows you to set up experiments where different " +
                "light sources are enabled for different cycles. If you " +
                "set a frequency of 5 for a given light, for example, " +
                "then that light will only be used for every 5th pass " +
                "(the 1st, 6th, 11th, etc. cycles). You can specify an " +
                "offset, too: \"5 + 1\" would enable the light for the " +
                "2nd, 7th, 12th, etc. cycles.")
        self.shouldCustomizeLightFrequencies.Bind(wx.EVT_CHECKBOX,
                self.onCustomizeLightFrequencies)
        self.lightFrequenciesPanel = wx.Panel(self.panel,
                style = wx.BORDER_SUNKEN | wx.TAB_TRAVERSAL)
        self.lightFrequencies, sizer = guiUtils.makeLightsControls(
                self.lightFrequenciesPanel,
                [str(l.wavelength) for l in self.allLights],
                self.settings['lightFrequencies'])
        self.lightFrequenciesPanel.SetSizerAndFit(sizer)
        self.lightFrequenciesPanel.Show(self.settings['shouldCustomizeLightFrequencies'])
        columnSizer.Add(self.lightFrequenciesPanel, 0,
                wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        controlsSizer.Add(columnSizer, 0, wx.ALL, 5)
        self.panelSizer.Add(controlsSizer)

        ## Controls whether or not the scanning experiment's parameters are
        # shown.
        self.showScanButton = wx.Button(self.panel, -1, "Show experiment settings")
        self.showScanButton.Bind(wx.EVT_BUTTON, self.onShowScanButton)
        self.panelSizer.Add(self.showScanButton, 0, wx.ALIGN_CENTER | wx.TOP, 5)
        ## This panel configures the experiment we perform when visiting sites.
        self.experimentPanel = experimentConfigPanel.ExperimentConfigPanel(
                self.panel, resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onExperimentPanelReset,
                configKey = 'multiSiteExperimentPanel')
        self.experimentPanel.filepath_panel.SetTemplate(_FILENAME_TEMPLATE)
        self.panelSizer.Add(self.experimentPanel, 0,
                wx.ALIGN_CENTER | wx.ALL, 5)
        self.experimentPanel.Hide()
        
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

        button = wx.Button(self.panel, -1, "Reset")
        button.SetToolTip(wx.ToolTip("Reload this window with all default values"))
        button.Bind(wx.EVT_BUTTON, self.onReset)
        buttonSizer.Add(button, 0, wx.ALL, 5)

        buttonSizer.Add((1, 0), 1, wx.EXPAND)

        button = wx.Button(self.panel, wx.ID_CANCEL, "Cancel")
        buttonSizer.Add(button, 0, wx.ALL, 5)
        
        button = wx.Button(self.panel, wx.ID_OK, "Start")
        button.SetToolTip(wx.ToolTip("Start the experiment"))
        button.Bind(wx.EVT_BUTTON, self.onStart)
        buttonSizer.Add(button, 0, wx.ALL, 5)

        self.panelSizer.Add(buttonSizer, 0, wx.ALL, 5)
        self.panel.SetSizerAndFit(self.panelSizer)
        self.sizer.Add(self.panel)
        self.SetSizerAndFit(self.sizer)


    ## User clicked the show/hide scanning experiment button.
    def onShowScanButton(self, event):
        self.experimentPanel.Show(not self.experimentPanel.IsShown())
        text = ['Show', 'Hide'][self.experimentPanel.IsShown()]
        self.showScanButton.SetLabel("%s experiment settings" % text)
        self.panel.SetSizerAndFit(self.panelSizer)
        self.SetClientSize(self.panel.GetSize())


    ## User checked/unchecked the "customize light frequencies" button.
    def onCustomizeLightFrequencies(self, event):
        self.lightFrequenciesPanel.Show(self.shouldCustomizeLightFrequencies.GetValue())
        self.panel.Layout()
        self.panel.SetSizerAndFit(self.panelSizer)
        self.SetClientSize(self.panel.GetSize())


    ## Our experiment panel resized itself.
    def onExperimentPanelResize(self, panel):
        self.panel.SetSizerAndFit(self.panelSizer)
        self.SetClientSize(self.panel.GetSize())


    ## Our experiment panel needs to be reset.
    def onExperimentPanelReset(self):
        self.panelSizer.Remove(self.experimentPanel)
        self.experimentPanel.Destroy()
        self.experimentPanel = experimentConfigPanel.ExperimentConfigPanel(
                self.panel, resizeCallback = self.onExperimentPanelResize,
                resetCallback = self.onExperimentPanelReset,
                configKey = 'multiSiteExperimentPanel')
        self.experimentPanel.filepath_panel.SetTemplate(_FILENAME_TEMPLATE)
        # Put the experiment panel back into the sizer immediately after
        # the button that shows/hides it.
        for i, item in enumerate(self.panelSizer.GetChildren()):
            if item.GetWindow() is self.showScanButton:
                self.panelSizer.Insert(i + 1, self.experimentPanel, 0,
                        wx.ALIGN_CENTER | wx.ALL, 5)
        self.panelSizer.Layout()
        self.Refresh()
        self.panel.SetSizerAndFit(self.panelSizer)
        return self.experimentPanel


    ## Analyze the user's chosen sites to visit and how often they should
    # be visited, and come up with a sequence of sites to visit on each
    # cycle that minimizes total travel time. Return a tuple of
    # (total number of site lists, mapping of cycle number to site list).
    def chooseSiteVisitOrder(self):
        (baseIndices, frequencies) = self.sitesPanel.getSitesList()
        # Check for sites that have been deleted
        baseOrder = []
        baseFrequencies = []
        for i, siteId in enumerate(baseIndices):
            if cockpit.interfaces.stageMover.doesSiteExist(siteId):
                baseOrder.append(siteId)
                baseFrequencies.append(frequencies[i])
        cycleRate = 1
        seenFreqs = set()
        # Generate a cycle rate (number of unique sets of sites to visit).
        # Our approach will result in some redundancies, but that's
        # not a huge deal.
        for freq in baseFrequencies:
            if freq not in seenFreqs:
                cycleRate *= freq
                seenFreqs.add(freq)
        cycleNumToSitesList = []
        for i in range(cycleRate):
            sitesList = []
            for siteId, frequency in zip(baseOrder, baseFrequencies):
                if i % frequency == 0:
                    sitesList.append(siteId)
            if self.shouldOptimizeSiteOrder.GetValue():
                cycleNumToSitesList.append(cockpit.interfaces.stageMover.optimisedSiteOrder(sitesList))
            else:
                cycleNumToSitesList.append(sitesList)
        return (cycleRate, cycleNumToSitesList)


    ## Run sanity checks before starting the experiment. Return True if all
    # is well, False otherwise.
    def sanityCheck(self):
        if not self.sitesPanel.getSitesList():
            wx.MessageBox("You must select sites before running the experiment.",
                    "Error", wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
            return False
        # Verify that all sites are reachable; the user may have
        # restarted the cockpit (thus resetting motion safeties) and then
        # loaded a list of sites which we cannot now reach.
        for siteId in self.sitesPanel.getSitesList()[0]:
            if not cockpit.interfaces.stageMover.doesSiteExist(siteId):
                wx.MessageBox("Experiment cancelled:\n\nSite %s does not exist." % siteId,
                        "Error", wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
                return False
            if not cockpit.interfaces.stageMover.canReachSite(siteId):
                wx.MessageBox("Experiment cancelled:\n\nSite %s cannot be reached." % siteId,
                        "Error", wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP)
                return False
        return True
    

    ## Run the experiment. We spin this off to a background thread so
    # the user can interact with the UI while the experiment runs.
    @cockpit.util.threads.callInNewThread
    def onStart(self, event = None):
        if not self.sanityCheck():
            return
        self.Hide()
        self.saveConfig()

        self.activeLights = [l.getIsEnabled() for l in self.allLights]
        
        self.shouldAbort = False
        delay = float(self.delayBeforeStarting.GetValue()) * 60
        self.waitFor(delay)
        if self.shouldAbort:
            return

        experimentStart = time.localtime()
        cycleDuration = 0
        if self.cycleDuration.GetValue():
            cycleDuration = float(self.cycleDuration.GetValue())
        cyclePeriod, cycleNumToSitesList = self.chooseSiteVisitOrder()
        numCycles = int(self.numCycles.GetValue())
        cycleStartTime = time.time()
        for cycleNum in range(numCycles):
            siteIds = cycleNumToSitesList[cycleNum % cyclePeriod]
            if cycleNum != 0:
                # Move to the first site.
                cockpit.interfaces.stageMover.waitForStop()
                cockpit.interfaces.stageMover.goToSite(siteIds[0], shouldBlock = True)
                # Wait for when the next cycle should start.
                waitTime = cycleStartTime + cycleDuration - time.time()
                if not self.waitFor(waitTime):
                    print ("Couldn't finish cycle in time; off by %.2f seconds" % (-waitTime))
            print ("Starting cycle",cycleNum,"of",numCycles,"at %.2f" % time.time())
            cycleStartTime = time.time()
            self.activateLights(cycleNum)
            for siteId in siteIds:
                if self.shouldAbort:
                    break
                print ("Imaging site",siteId,"at %.2f" % time.time())
                self.imageSite(siteId, cycleNum, experimentStart)

            if self.shouldAbort:
                break
            if self.shouldAbort:
                break

        self.cleanUp()


    ## Clean up after the experiment ends.
    def cleanUp(self):
        for i, shouldActivate in enumerate(self.activeLights):
            self.allLights[i].setEnabled(shouldActivate)
        if (self.shouldPowerDownWhenDone is not None and
                self.shouldPowerDownWhenDone.GetValue()):
            handlers = depot.getHandlersOfType(depot.POWER_CONTROL)
            for handler in handlers:
                handler.disable()
        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting', '')


    ## Select the appropriate light sources for this cycle.
    def activateLights(self, cycleNum):
        for i, control in enumerate(self.lightFrequencies):
            string = control.GetValue()
            frequency = 1
            offset = 0
            if '+' in string:
                # There's both a frequency and an offset.
                frequency, offset = [int(s) for s in string.split('+')]
            else:
                # Just a frequency.
                frequency = int(string)
            # Only activate a light if it was enabled when the experiment
            # started.
            if self.activeLights[i]:
                self.allLights[i].setEnabled(cycleNum % frequency == offset)


    ## Go to the specified site and run our experiment on it.
    def imageSite(self, siteId, cycleNum, experimentStart):
        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                       'Waiting for stage motion')
        cockpit.interfaces.stageMover.waitForStop()
        cockpit.interfaces.stageMover.goToSite(siteId, shouldBlock = True)
        self.waitFor(float(self.delayBeforeImaging.GetValue()))
        if self.shouldAbort:
            return
        # Try casting the site ID to an int, which it probably is, so that
        # we can use %03d (fills with zeros) instead of %s (variable width,
        # so screws with sorting).
        try:
            siteId = '%03d' % int(siteId)
        except ValueError:
            # Not actually an int.
            pass
        self.experimentPanel.filepath_panel.UpdateFilename({
            "date": time.strftime('%Y%m%d', experimentStart),
            "time": time.strftime('%H%M', experimentStart),
            "cycle": ("%03d" % cycleNum),
            "site": siteId,
        })
        start = time.time()
        events.executeAndWaitFor(events.EXPERIMENT_COMPLETE,
                self.experimentPanel.runExperiment)
        print ("Imaging took %.2fs" % (time.time() - start))


    ## User clicked the abort button.
    def onAbort(self, *args):
        self.shouldAbort = True


    ## Wait for some time, allowing the user to abort the wait. Return True
    # if we were successful (i.e. handed a valid amount of time to wait for).
    def waitFor(self, seconds):
        if seconds <= 0:
            return False
        print ("Waiting for %.2f seconds" % seconds)
        endTime = time.time() + seconds
        curTime = time.time()
        while curTime < endTime and not self.shouldAbort:
            if int(curTime + .25) != int(curTime):
                remaining = endTime - curTime
                # Advanced to a new second; update the status light.
                displayMinutes = remaining // 60
                displaySeconds = (remaining - displayMinutes * 60) // 1
                events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting',
                               ('Waiting for %02d:%02d'
                                % (displayMinutes, displaySeconds)))
            time.sleep(.25)
            curTime = time.time()
        return True
 

    ## Save our settings to the config.
    def saveConfig(self):
        lightFrequencies = [l.GetValue() for l in self.lightFrequencies]
        cockpit.util.userConfig.setValue('multiSiteExperiment',
                {
                    'numCycles': self.numCycles.GetValue(),
                    'cycleDuration': self.cycleDuration.GetValue(),
                    'delayBeforeStarting': self.delayBeforeStarting.GetValue(),
                    'delayBeforeImaging': self.delayBeforeImaging.GetValue(),
                    'fileBase': self.fileBase.GetValue(),
                    'shouldCustomizeLightFrequencies': self.shouldCustomizeLightFrequencies.GetValue(),
                    'shouldOptimizeSiteOrder': self.shouldOptimizeSiteOrder.GetValue(),
                    'lightFrequencies': lightFrequencies,
                }
        )

    ## Blow away the dialog and recreate it from scratch.
    def onReset(self, event):
        parent = self.GetParent()
        global dialog
        dialog.Destroy()
        dialog = None
        showDialog(parent)



## Global singleton
dialog = None


def showDialog(parent):
    global dialog
    if not dialog:
        dialog = MultiSiteExperimentDialog(parent)
    dialog.Show()
