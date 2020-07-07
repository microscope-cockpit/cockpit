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
from cockpit.gui.macroStage.macroStageZ import MacroStageZ
from cockpit.interfaces import stageMover


class HandlerPositionCtrl(wx.TextCtrl):
    def __init__(self, parent, axis: int, handler_index: int) -> None:
        super().__init__(parent, style=wx.TE_RIGHT|wx.TE_READONLY)
        self._axis = axis
        self._handler_index = handler_index

        if self._handler_index != stageMover.getCurHandlerIndex():
            self.Disable()

        for event, handler in [(cockpit.events.STAGE_POSITION, self._OnMove),
                               ('stage step index', self._OnHandlerChange)]:
            emitter = cockpit.gui.EvtEmitter(self, event)
            emitter.Bind(cockpit.gui.EVT_COCKPIT, handler)

    def _OnMove(self, event: wx.CommandEvent) -> None:
        axis = event.EventData[0]
        if axis == self._axis:
            pos = stageMover.getAllPositions()[self._handler_index][self._axis]
            self.SetValue('%5.2f' % pos)

    def _OnHandlerChange(self, event: wx.CommandEvent) -> None:
        new_handler_index = event.EventData[0]
        if new_handler_index == self._handler_index:
            self.Enable()
        else:
            self.Disable()


class AxisStepCtrl(wx.TextCtrl):
    """Text control to display step size for one axis.

    Unlike the controls in :mod:`cockpit.gui.safeControls` this
    control does not require affirmative action, i.e., the user is not
    required to press enter to confirm the value.  Simply selecting
    another control or window will attempt to set the new step size.
    This is because the step size value is not critical in that
    setting an incorrect value by accident does not have consequences.

    However, like the safe controls, if the value is not valid, empty
    or non-numeric for example, then it returns to the previous,
    valid, value.

    """
    def __init__(self, parent, axis: int) -> None:
        super().__init__(parent, style=wx.TE_RIGHT)
        self._axis = axis

        self._SetStepSizeValue(stageMover.getCurStepSizes()[self._axis])

        # When we gain focus we will update the last value.  When we
        # then lose focus we set the new step size.  If that fails,
        # probably because it's invalid, we can revert back to the
        # previous step size.
        self._last_value = self.GetValue() # type: str
        self.Bind(wx.EVT_KILL_FOCUS, self._OnKillFocus)
        self.Bind(wx.EVT_SET_FOCUS, self._OnSetFocus)

        step_size = cockpit.gui.EvtEmitter(self, 'stage step size')
        step_size.Bind(cockpit.gui.EVT_COCKPIT, self._OnStepSizeChange)


    def _SetStepSizeValue(self, step_size: float) -> None:
        self.SetValue('%4.2f' % step_size)


    def _OnStepSizeChange(self, event: cockpit.gui.CockpitEvent) -> None:
        axis, step_size = event.EventData
        if axis != self._axis:
            event.Skip()
        else:
            self._SetStepSizeValue(step_size)


    def _OnSetFocus(self, event: wx.FocusEvent) -> None:
        # Record value so that we can revert to it if we later fail to
        # set the new value.
        self._last_value = self.GetValue()
        event.Skip()

    def _OnKillFocus(self, event: wx.FocusEvent) -> None:
        try:
            new_step_size = float(self.GetValue())
            wx.GetApp().Stage.SetStepSize(self._axis, new_step_size)
        except:
            self.ChangeValue(self._last_value)
        else:
            self._last_value = self.GetValue()
        event.Skip()


class AxesPositionPanel(wx.Panel):
    """A panel showing the position and step size of some axis and stage."""
    def __init__(self, parent, axes: typing.Sequence[str],
                 *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        for axis_name in axes:
            if axis_name not in stageMover.AXIS_MAP:
                raise ValueError('unknown axis named\'%s\'' % axis_name)

        n_stages = cockpit.interfaces.stageMover.mover.n_stages
        positions = [] # type: typing.List[typing.List[AxisPositionCtrl]]
        step_sizes = [] # type: typing.List[StageStepCtrl]
        for axis_name in axes:
            axis_index = stageMover.AXIS_MAP[axis_name]
            axis_positions = [] # type: typing.List[AxisPositionCtrl]
            for handler_index in range(n_stages):
                position = HandlerPositionCtrl(self, axis=axis_index,
                                               handler_index=handler_index)
                axis_positions.append(position)
            positions.append(axis_positions)
            step_sizes.append(AxisStepCtrl(self, axis=axis_index))

        sizer = wx.FlexGridSizer(3 + n_stages)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        for i, axis_name in enumerate(axes):
            sizer.Add(wx.StaticText(self, label=axis_name + ':'),
                      flags=wx.SizerFlags().Centre())
            for position in positions[i]:
                sizer.Add(position)
            sizer.Add(wx.StaticText(self, label='step (µm):'),
                      flags=wx.SizerFlags().Centre().Border(wx.LEFT))
            sizer.Add(step_sizes[i])
        self.SetSizer(sizer)


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

        sizer_flags = wx.SizerFlags(1)
        expand_sizer_flags = wx.SizerFlags(sizer_flags).Expand()

        sizer.Add(save_top, expand_sizer_flags)
        sizer.Add(self._top_ctrl, expand_sizer_flags)
        sizer.Add(go_to_top, expand_sizer_flags)

        sizer.Add(wx.StaticText(self, label='z-height (µm):'),
                  wx.SizerFlags(sizer_flags).Centre())
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
class MacroStagePanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # For relative sizing of items. The overall window is
        # (width * 10) by (height * 8) pixels. The ratio of
        # these two values is important for proper drawing.
        # FIXME: this is not drawing properly (issue #585).  The fix
        # should be on the MacroStage canvas themselves which should
        # need a specific size and draw on whatever space is available
        # to them.
        width = 84
        height = width * 2 / 3.0

        # Remember that, in classic "row means X, right?" fashion,
        # WX has flipped its position and size tuples, so
        # (7, 4) means an X position (or width) of 4, and a Y
        # position/height of 7.

        xy_stage = MacroStageXY(self, size=(width*4, height*6))
        z_stage = MacroStageZ(self, size=(width*5, height*6))

        xyz_coords = AxesPositionPanel(self, axes=['X', 'Y', 'Z'])

        def make_button(label: str, handler: typing.Callable,
                        tooltip: str = '') -> wx.Button:
            btn = wx.Button(self, label=label)
            btn.SetToolTip(tooltip)
            btn.Bind(wx.EVT_BUTTON, handler)
            return btn

        xy_safeties_btn = make_button('Set XY safeties', xy_stage.setSafeties,
                                      'Click twice on the XY Macro Stage view'
                                      ' to set the XY motion limits.')
        z_safeties_btn = make_button('Set Z safeties', self.OnSetZSafeties)
        switch_btn = make_button('Switch control', self.OnSwitchControl,
                                 'Change which stage motion device the keypad'
                                 ' controls.')
        recenter_btn = make_button('Recenter', self.OnRecenter)
        touch_down_btn = make_button('Touch down', self.OnTouchDown,
                                     'Bring the stage down to touch slide')

        top_bottom_panel = SaveTopBottomPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)

        stage_sizer = wx.BoxSizer(wx.HORIZONTAL)
        stage_sizer.Add(xy_stage)
        stage_sizer.Add(z_stage)
        sizer.Add(stage_sizer)

        buttons_sizer = wx.GridSizer(cols=0, rows=1, gap=(0,0))
        for btn in [xy_safeties_btn,
                    switch_btn,
                    recenter_btn,
                    z_safeties_btn,
                    touch_down_btn]:
            buttons_sizer.Add(btn, wx.SizerFlags().Expand().Border())
        sizer.Add(buttons_sizer, wx.SizerFlags().Centre())

        coords_sizer = wx.BoxSizer(wx.HORIZONTAL)
        coords_sizer.Add(xyz_coords, wx.SizerFlags().Border())
        coords_sizer.Add(top_bottom_panel, wx.SizerFlags().Border())
        sizer.Add(coords_sizer, wx.SizerFlags().Centre())

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


class MacroStageWindow(wx.Frame):
    SHOW_DEFAULT = True
    def __init__(self, parent, title='Macro Stage'):
        super().__init__(parent, title=title)
        panel = MacroStagePanel(self)
        sizer = wx.BoxSizer()
        sizer.Add(panel)
        self.SetSizerAndFit(sizer)


def makeWindow(parent):
    window = MacroStageWindow(parent)
