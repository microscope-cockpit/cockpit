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

from cockpit.interfaces import stageMover


## @package saveTopBottomPanel
# This module handles code related to the UI widget for saving the current
# stage altitude as a "top" or "bottom".


class SaveTopBottomPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # TODO: might be simpler to just use a raised border instead,
        # or maybe this should be done by the parent that wants to
        # insert this box.
        box = wx.StaticBox(self)

        self._top_ctrl = wx.TextCtrl(box, style=wx.TE_RIGHT, size=(60, -1))
        self._top_ctrl.Bind(wx.EVT_TEXT, self.OnEditPosition)

        self._bottom_ctrl = wx.TextCtrl(box, style=wx.TE_RIGHT, size=(60, -1))
        self._bottom_ctrl.Bind(wx.EVT_TEXT, self.OnEditPosition)

        self._height_ctrl = wx.StaticText(box, style=wx.TE_RIGHT, size=(60, -1))

        self._top_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedTop)
        self._bottom_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedBottom)
        self._UpdateHeight()

        for ctrl in [self._top_ctrl, self._height_ctrl, self._bottom_ctrl]:
            ctrl.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL))

        def make_button(label: str, handler: typing.Callable) -> wx.Button:
            btn = wx.Button(box, label=label, size=(75, -1))
            btn.Bind(wx.EVT_BUTTON, handler)
            return btn

        save_top = make_button('Save top', self.OnSaveTop)
        save_bottom = make_button('Save bottom', self.OnSaveBottom)
        go_to_top = make_button('Go to top', self.OnGoToTop)
        go_to_centre = make_button('Go to centre', self.OnGoToCentre)
        go_to_bottom = make_button('Go to bottom', self.OnGoToBottom)

        box_sizer = wx.StaticBoxSizer(box)

        sizer = wx.FlexGridSizer(rows=3, cols=3, gap=(0, 0))
        sizer_flags = wx.SizerFlags(0).Centre()

        sizer.Add(save_top, sizer_flags.Border(wx.ALL, 1))
        sizer.Add(self._top_ctrl,
                  sizer_flags.Border(wx.ALL, 1).Proportion(1))
        sizer.Add(go_to_top, sizer_flags.Border(wx.ALL, 1))

        sizer.Add(wx.StaticText(box, label='z-height (µm):'),
                  sizer_flags.Border(wx.ALL, 5))
        sizer.Add(self._height_ctrl, sizer_flags.Border(wx.ALL, 1))
        sizer.Add(go_to_centre, sizer_flags.Border(wx.ALL, 1))

        sizer.Add(save_bottom, sizer_flags.Border(wx.ALL, 1))
        sizer.Add(self._bottom_ctrl,
                  sizer_flags.Border(wx.ALL, 1).Proportion(1))
        sizer.Add(go_to_bottom, sizer_flags.Border(wx.ALL, 1))

        box_sizer.Add(sizer)
        self.SetSizer(box_sizer)


    def _UpdateHeight(self) -> None:
        """When saved top and bottom are changed, this needs to be updated."""
        # FIXME: this should be done as handling of an event from the
        # stageMover itself.
        self._height_ctrl.SetLabel('%.2f' % (stageMover.mover.SavedTop
                                             - stageMover.mover.SavedBottom))

    def OnSaveTop(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedTop = stageMover.getPosition()[2]
        self._top_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedTop)
        self._UpdateHeight()

    def OnSaveBottom(self, evt: wx.CommandEvent) -> None:
        stageMover.mover.SavedBottom = stageMover.getPosition()[2]
        self._bottom_ctrl.ChangeValue('%.1f' % stageMover.mover.SavedBottom)
        self._UpdateHeight()


    def OnEditPosition(self, evt: wx.CommandEvent) -> None:
        """Event for typing into one of the save top/bottom text controls."""
        stageMover.mover.SavedTop = float(self._top_ctrl.GetValue())
        stageMover.mover.SavedBottom = float(self._bottom_ctrl.GetValue())
        self._UpdateHeight()

    def OnGoToTop(self, evt: wx.CommandEvent) -> None:
        stageMover.moveZCheckMoverLimits(stageMover.mover.SavedTop)

    def OnGoToBottom(self, evt: wx.CommandEvent) -> None:
        stageMover.moveZCheckMoverLimits(stageMover.mover.SavedBottom)

    def OnGoToCentre(self, evt: wx.CommandEvent) -> None:
        centre = (stageMover.mover.SavedBottom
                  + ((stageMover.mover.SavedTop
                      - stageMover.mover.SavedBottom) / 2.0))
        stageMover.moveZCheckMoverLimits(centre)
