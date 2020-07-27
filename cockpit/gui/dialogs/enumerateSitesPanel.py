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


import cockpit.gui.guiUtils
import cockpit.util.logger
import cockpit.interfaces.stageMover

import wx


## @package dialogs.enumerateSitesPanel
# This module contains the EnumerateSitesPanel class

## This class provides a standard way to list out sites -- saved positions
# in interfaces.stageMover, which each have a corresponding number when
# displayed in the mosaic. For example, the string "1,2,4-6,8-10" corresponds
# to the list of sites [1,2,4,5,6,8,9,10].
# Additionally, numbers in parentheses may be included to indicate
# a frequency. E.g. "1,2-4(2),5-8(3)" would mean "1 always, 2-4 every other
# time, 5-8 every third time".
class EnumerateSitesPanel(wx.Panel):
    def __init__(self, parent, label, id = -1, size = (200, -1),
                 minSize = (280, -1), defaultIsAllSites = True):
        super().__init__(parent, id)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sites = cockpit.gui.guiUtils.addLabeledInput(parent = self, 
                sizer = sizer,
                label = label, defaultValue = '',
                size = size, minSize = minSize)
        self.sites.SetToolTip(wx.ToolTip("Comma-delimited, or with range " +
                "indicators, for example:\n1, 3, 5-10, 14, 17-23\n" +
                "You may also include frequencies in parentheses, e.g.\n" +
                "1-4,5(2),6-10(4)\n" +
                "to use sites 1-4 every time, site 5 every other time, " +
                "and sites 6-10 every fourth time."))

        siteListStr = 'Most recent site'
        if defaultIsAllSites:
            sites = cockpit.interfaces.stageMover.getAllSites()
            if not sites:
                siteListStr = "You must select points first"
            else:
                siteListStr = '1-%d' % sites[-1].uniqueID
        self.sites.SetValue(siteListStr)

        self.SetSizerAndFit(sizer)


    def getSitesList(self):
        # Construct the input list of sites
        sitesString = self.sites.GetValue()
        if sitesString == "Most recent site":
            return ([-1], [1])
        try:
            siteTokens = self.sites.GetValue().split(',')
            baseIndices = []
            baseFrequencies = []
            for token in siteTokens:
                # Yeah, I could use regexes for this...but I'm lazy
                frequency = 1
                if token.find('(') != -1:
                    # Extract frequency
                    token, frequency = token.split('(')
                    frequency = int(frequency.split(')')[0])
                if token.find('-') != -1:
                    first, last = token.split('-')
                    # These ranges are inclusive, so add 1 to last
                    newIndices = [i for i in range(int(first), int(last) + 1)
                                  if cockpit.interfaces.stageMover.doesSiteExist(i)]
                    baseIndices.extend(newIndices)
                    baseFrequencies.extend([frequency] * len(newIndices))
                elif cockpit.interfaces.stageMover.doesSiteExist(int(token)):
                    baseIndices.append(int(token))
                    baseFrequencies.append(frequency)
                
            return (baseIndices, baseFrequencies)
        except Exception as e:
            cockpit.util.logger.log.warning("Invalid site list \"%s\"; returning no sites", self.sites.GetValue())
            return []
