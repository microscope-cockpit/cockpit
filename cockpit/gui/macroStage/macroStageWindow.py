#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import typing

import wx

import cockpit.events
import cockpit.gui
import cockpit.gui.dialogs.safetyMinDialog
import cockpit.gui.keyboard
from cockpit.gui.macroStage.macroStageXY import MacroStageXY
from cockpit.gui.macroStage.macroStageZ import MacroStageZ, MacroStageZKey
from cockpit.interfaces import stageMover


class SaveTopBottomPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._top_ctrl = wx.TextCtrl(self, style=wx.TE_RIGHT)
        self._top_ctrl.Bind(wx.EVT_TEXT, self.OnEditTopPosition)

        self._bottom_ctrl = wx.TextCtrl(self, style=wx.TE_RIGHT)
        self._bottom_ctrl.Bind(wx.EVT_TEXT, self.OnEditBottomPosition)

        self._height_ctrl = wx.TextCtrl(self, style=wx.TE_RIGHT|wx.TE_READONLY)
        self._height_ctrl.Disable()

        # Fill in the text controls with current values.
        self.UpdateSavedPositions(None)

        def make_button(label: str, handler: typing.Callable) -> wx.Button:
            btn = wx.Button(self, label=label)
            btn.Bind(wx.EVT_BUTTON, handler)
            return btn

        save_top = make_button('Save top', self.OnSaveTop)
        save_bottom = make_button('Save bottom', self.OnSaveBottom)
        go_to_top = make_button('Go to top', self.OnGoToTop)
        go_to_centre = make_button('Go to centre', self.OnGoToCentre)
        go_to_bottom = make_button('Go to bottom', self.OnGoToBottom)

        listener = cockpit.gui.EvtEmitter(self,cockpit.events.STAGE_TOP_BOTTOM)
        listener.Bind(cockpit.gui.EVT_COCKPIT, self.UpdateSavedPositions)

        sizer = wx.GridSizer(rows=3, cols=3, gap=(0, 0))

        sizer_flags = wx.SizerFlags(1).Border()
        expand_sizer_flags = wx.SizerFlags(sizer_flags).Expand()

        sizer.Add(save_top, expand_sizer_flags)
        sizer.Add(self._top_ctrl, expand_sizer_flags)
        sizer.Add(go_to_top, expand_sizer_flags)

        sizer.Add(wx.StaticText(self, label='z-height (µm):'),
                  wx.SizerFlags(sizer_flags).CentreVertical().Right())
        sizer.Add(self._height_ctrl, expand_sizer_flags)
        sizer.Add(go_to_centre, expand_sizer_flags)

        sizer.Add(save_bottom, expand_sizer_flags)
        sizer.Add(self._bottom_ctrl, expand_sizer_flags)
        sizer.Add(go_to_bottom, expand_sizer_flags)

        self.SetSizer(sizer)


    def OnSaveTop(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedTop = stageMover.getPosition()[2]

    def OnSaveBottom(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedBottom = stageMover.getPosition()[2]

    def UpdateSavedPositions(self, evt: wx.CommandEvent) -> None:
        self._top_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedTop)
        self._bottom_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedBottom)
        self._height_ctrl.ChangeValue('%.2f' % (stageMover.mover.SavedTop
                                                - stageMover.mover.SavedBottom))

    def OnEditTopPosition(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedTop = float(self._top_ctrl.GetValue())

    def OnEditBottomPosition(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedBottom = float(self._bottom_ctrl.GetValue())

    def OnGoToTop(self, evt: wx.CommandEvent) -> None:
        stageMover.moveZCheckMoverLimits(stageMover.mover.SavedTop)

    def OnGoToBottom(self, evt: wx.CommandEvent) -> None:
        stageMover.moveZCheckMoverLimits(stageMover.mover.SavedBottom)

    def OnGoToCentre(self, evt: wx.CommandEvent) -> None:
        centre = (stageMover.mover.SavedBottom
                  + ((stageMover.mover.SavedTop
                      - stageMover.mover.SavedBottom) / 2.0))
        stageMover.moveZCheckMoverLimits(centre)


## This class simply contains instances of the various MacroStage
# subclasses, side-by-side, along with the buttons associated
# with each. It also allows for communication between
# the different subclasses, and has some logic that is generally
# related to the UIs the MacroStage instances provide but is not
# tightly bound to any one of them.
class MacroStageWindow(wx.Frame):
    SHOW_DEFAULT = True
    def __init__(self, parent, title='Macro Stage'):
        super().__init__(parent, title=title)

        # For relative sizing of items. The overall window is
        # (width * 10) by (height * 8) pixels. The ratio of
        # these two values is important for proper drawing.
        width = 84
        height = width * 2 / 3.0

        # I apologize for the use of the GridBagSizer here. It's
        # necessary because of the odd shape of the Z macro
        # stage, which is wider than the other elements in its
        # "column".
        #
        #  0     1     2     3     4     5     6     7     8     9     0     1
        #  |------------------------------------------------------------------
        #  |                       |     |                             |     |
        #  |                       |     |                             |     |
        # 1|                       |     |                             |     |
        #  |                       |     |                             |     |
        #  |                       |     |                             |     |
        # 2|                       |     |                             |     |
        #  |                       |     |                             |     |
        #  |     MacroStageXY      |     |                             |     |
        # 3|                       |     |           MacroStageZ       |     |
        #  |                       |     |                             |     |
        #  |                       |     |                             |     |
        # 4|                       |     |                             |     |
        #  |                       |     |                             |     |
        #  |                       |     |                             |     |
        # 5|                       |     |                             |     |
        #  |                       |     |                             |     |
        #  |                       |     |                             |     |
        # 6|                       |     |------------------------------------
        #  |                       |     |  macroStageZKey |                 |
        #  |                       |     |                 |       Save      |
        # 7|-----------------------|     |---------------- |     TopBottom   |
        #  |       XY buttons      |     |    Z buttons    |       Panel     |
        #  |                       |     |                 |                 |
        # 8|------------------------------------------------------------------
        #
        # Remember that, in classic "row means X, right?" fashion,
        # WX has flipped its position and size tuples, so
        # (7, 4) means an X position (or width) of 4, and a Y
        # position/height of 7.

        xy_stage = MacroStageXY(self, size=(width*4, height*7))
        z_stage = MacroStageZ(self, size=(width*5, height*6))

        z_key = MacroStageZKey(self, size=(width*3, height*1))

        def make_button(label: str, handler: typing.Callable,
                        tooltip: str = '') -> wx.Button:
            btn = wx.Button(self, label=label)
            btn.SetToolTip(tooltip)
            btn.Bind(wx.EVT_BUTTON, handler)
            return btn

        xy_safeties_btn = make_button('Set safeties', xy_stage.setSafeties,
                                      'Click twice on the XY Macro Stage view'
                                      ' to set the XY motion limits.')

        z_safeties_btn = make_button('Set safeties', self.OnSetZSafeties)

        switch_btn = make_button('Switch control', self.OnSwitchControl,
                                 'Change which stage motion device the keypad'
                                 ' controls.')

        recenter_btn = make_button('Recenter', self.OnRecenter)

        touch_down_btn = make_button('Touch down', self.OnTouchDown,
                                     'Bring the stage down to touch slide')

        # StaticBox and StaticBoxSizer are a bit weird in that the
        # sizer needs to be the parent of the controls inside the box.
        # We should probably be using a bordered style instead of a
        # static box without a label.
        top_bottom_sizer = wx.StaticBoxSizer(wx.VERTICAL, parent=self)
        top_bottom_sizer.Add(SaveTopBottomPanel(top_bottom_sizer.GetStaticBox()))


        self.SetBackgroundColour((255, 255, 255))

        sizer = wx.GridBagSizer()

        xy_sizer = wx.BoxSizer(wx.VERTICAL)
        xy_sizer.Add(xy_stage)
        xy_buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for btn in [xy_safeties_btn, switch_btn, recenter_btn]:
            xy_buttons_sizer.Add(btn)
        xy_sizer.Add(xy_buttons_sizer)
        sizer.Add(xy_sizer, pos=(0, 0), span=(8, 4))

        sizer.Add(z_stage, pos=(0, 5), span=(6, 5))
        sizer.Add(z_key, pos=(6, 5), span=(1, 3))
        z_buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for btn in [z_safeties_btn, touch_down_btn]:
            z_buttons_sizer.Add(btn)
        sizer.Add(z_buttons_sizer, pos=(7, 5), span=(1, 3))

        sizer.Add(top_bottom_sizer, pos=(6, 8), span=(2, 3))

        self.SetSizerAndFit(sizer)

        cockpit.gui.keyboard.setKeyboardHandlers(self)


    def OnSwitchControl(self, evt: wx.CommandEvent) -> None:
        stageMover.changeMover()

    def OnRecenter(self, evt: wx.CommandEvent) -> None:
        stageMover.recenterFineMotion()

    def OnSetZSafeties(self, evt: wx.CommandEvent) -> None:
        cockpit.gui.dialogs.safetyMinDialog.showDialog(self)

    def OnTouchDown(self, ect: wx.CommandEvent) -> None:
        zpos = wx.GetApp().Config['stage'].getfloat('slideTouchdownAltitude')
        stageMover.goToZ(zpos)


def makeWindow(parent):
    window = MacroStageWindow(parent)
