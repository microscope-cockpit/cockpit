import gui.guiUtils
import util.logger
import interfaces.stageMover

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
        wx.Panel.__init__(self, parent, id)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sites = gui.guiUtils.addLabeledInput(parent = self, 
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
            sites = interfaces.stageMover.getAllSites()
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
                    newIndices = range(int(first), int(last) + 1)
                    newIndices = filter(interfaces.stageMover.doesSiteExist, newIndices)
                    baseIndices.extend(newIndices)
                    baseFrequencies.extend([frequency] * len(newIndices))
                elif interfaces.stageMover.doesSiteExist(int(token)):
                    baseIndices.append(int(token))
                    baseFrequencies.append(frequency)
                
            return (baseIndices, baseFrequencies)
        except Exception, e:
            util.logger.log.warn("Invalid site list \"%s\"; returning no sites", self.sites.GetValue())
            return []
