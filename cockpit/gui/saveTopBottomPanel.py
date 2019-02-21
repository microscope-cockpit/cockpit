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


import cockpit.interfaces.stageMover
import cockpit.util.userConfig
import wx

## @package saveTopBottomPanel
# This module handles code related to the UI widget for saving the current
# stage altitude as a "top" or "bottom".
# \todo This should be a proper singleton class instead of a bunch of functions
# and module-level variables.

## Text control for the altitude at the "top"
topPosControl = None
## Text control for the altitude at the "bottom"
bottomPosControl = None
## Text label for the total height of the stack. 
zStackHeightLabel = None

savedTop = None
savedBottom = None

## Create and lay out the "save top/bottom" panel, which allows the user to 
# remember Z levels of interest.
def createSaveTopBottomPanel(parent):
    global topPosControl, zStackHeightLabel, bottomPosControl,savedTop,savedBottom

    ## Current saved top position stored in user config file.
    savedTop = cockpit.util.userConfig.getValue('savedTop', default=3010)
    savedBottom = cockpit.util.userConfig.getValue('savedBottom', default=3000)

    panel = wx.Panel(parent, 8910)
    box = wx.StaticBox(panel, -1, '')
    
    sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
    panel.SetSizer(sizer)

    box = wx.FlexGridSizer(3, 3, 0, 0)
    sizer.Add(box, 0, wx.ALIGN_CENTER | wx.ALL, 1)

    saveTop = wx.Button(panel, 8911 , "Save top", size=(75, -1))
    box.Add(saveTop, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    topPosControl = wx.TextCtrl(panel, 8913, '0', style = wx.TE_RIGHT,size = (60, -1))
    box.Add(topPosControl, 1, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoTop = wx.Button(panel, 8915, "Go to top", size = (75, -1))
    box.Add(gotoTop, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    label = wx.StaticText(panel, -1, u"z-height (\u03bcm):")
    box.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)

    zStackHeightLabel = wx.StaticText(panel, -1, '0', 
            style = wx.TE_RIGHT, size = (60, -1))
    box.Add(zStackHeightLabel, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoCenter = wx.Button(panel, 8917, "Go to center", size = (75, -1))
    box.Add(gotoCenter, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    saveBot = wx.Button(panel, 8912, "Save bottom", size = (75, -1))
    box.Add(saveBot, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    bottomPosControl  = wx.TextCtrl(panel, 8914, '0', 
            style = wx.TE_RIGHT, size = (60, -1))
    box.Add(bottomPosControl, 1, wx.ALIGN_CENTRE | wx.ALL, 1)

    gotoBottom = wx.Button(panel, 8916, "Go to bottom", size = (75, -1))
    box.Add(gotoBottom, 0, wx.ALIGN_CENTRE | wx.ALL, 1)

    topPosControl.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    bottomPosControl.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    zStackHeightLabel.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))
    
    panel.SetAutoLayout(1)
    sizer.Fit(panel)

    topPosControl.SetValue("%.1f" % savedTop)
    bottomPosControl.SetValue("%.1f" % savedBottom)
    updateZStackHeight()
    
    parent.Bind(wx.EVT_BUTTON, OnTB_saveTop, id=8911 )
    parent.Bind(wx.EVT_BUTTON, OnTB_saveBottom, id=8912)
    parent.Bind(wx.EVT_BUTTON, OnTB_gotoTop, id=8915)
    parent.Bind(wx.EVT_BUTTON, OnTB_gotoBottom, id=8916)
    parent.Bind(wx.EVT_TEXT, OnTB_TextEdit, id=8913)
    parent.Bind(wx.EVT_TEXT, OnTB_TextEdit, id=8914)

    parent.Bind(wx.EVT_BUTTON, OnTB_gotoCenter, id=8917)
    return panel
    

## Event for handling users clicking on the "save top" button. Set savedTop.
def OnTB_saveTop(ev):
    global savedTop
    savedTop = cockpit.interfaces.stageMover.getPosition()[2]
    topPosControl.SetValue("%.1f" % savedTop)
    updateZStackHeight()
    cockpit.util.userConfig.setValue('savedTop', savedTop)

## Event for handling users clicking on the "save bottom" button. Set 
# savedBottom.
def OnTB_saveBottom(ev):
    global savedBottom
    savedBottom = cockpit.interfaces.stageMover.getPosition()[2]
    bottomPosControl.SetValue("%.1f" % savedBottom)
    updateZStackHeight()
    cockpit.util.userConfig.setValue('savedBottom', savedBottom)

## Event for handling users clicking on the "go to top" button. Use the 
# nanomover (and, optionally, also the stage piezo) to move to the target
# elevation.
def OnTB_gotoTop(ev):
    moveZCheckMoverLimits(savedTop)
        
## As OnTB_gotoTop, but for the bottom button instead.
def OnTB_gotoBottom(ev):
    moveZCheckMoverLimits(savedBottom)

## As OnTB_gotoTop, but for the middle button instead. 
def OnTB_gotoCenter(ev):
    target = savedBottom + ((savedTop - savedBottom) / 2.0)
    moveZCheckMoverLimits(target)


def moveZCheckMoverLimits(target):
    #Need to check current mover limits, see if we exceed them and if
    #so drop down to lower mover handler.
    originalMover= cockpit.interfaces.stageMover.mover.curHandlerIndex
    limits = cockpit.interfaces.stageMover.getIndividualSoftLimits(2)
    currentPos= cockpit.interfaces.stageMover.getPosition()[2]
    offset = target - currentPos


    ##IMD 2018-11-07 I think this test needs to be currentpos of the
    ##current mover not the overall pos.
    while (cockpit.interfaces.stageMover.mover.curHandlerIndex >= 0):
        handler=cockpit.interfaces.stageMover.mover.curHandlerIndex
        moverPos=cockpit.interfaces.stageMover.getAllPositions()[handler][2]
        if ((moverPos + offset)> limits[cockpit.interfaces.stageMover.mover.curHandlerIndex][1] or
            (moverPos + offset) < limits[cockpit.interfaces.stageMover.mover.curHandlerIndex][0]):
            # need to drop down a handler to see if next handler can do the move
            cockpit.interfaces.stageMover.mover.curHandlerIndex -= 1
            if (cockpit.interfaces.stageMover.mover.curHandlerIndex < 0):
                print ("Move too large for any Z mover.")
            
        else: 
            cockpit.interfaces.stageMover.goToZ(target)
            break

    #retrun to original active mover.
    cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover
        

## Event for when users type into one of the text boxes for the save top/bottom
# controls. Automatically update the saved top and bottom values.
def OnTB_TextEdit(ev):
    global savedTop, savedBottom
    savedBottom = float(bottomPosControl.GetValue())
    savedTop = float(topPosControl.GetValue())
    updateZStackHeight()


## Whenever the saved top/bottom are changed, this is called to update the 
# displayed distance between the two values.
def updateZStackHeight():
    zStackHeightLabel.SetLabel("%.2f" % (savedTop - savedBottom))


## Get the bottom and top of the stack.
def getBottomAndTop():
    return (savedBottom, savedTop)
