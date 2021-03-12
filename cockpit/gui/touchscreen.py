#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2018-2019 Mick Phillips <mick.phillips@gmail.com>
# Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
# Copyright (C) 2021 Danail Stoychev <danail.stoychev@exeter.ox.ac.uk>
#
# This file is part of Cockpit.
#
# Cockpit is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Cockpit is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys

import wx
import wx.lib.newevent
import wx.lib.scrolledpanel

import cockpit.gui
import cockpit.gui.freetype
import cockpit.gui.keyboard
import cockpit.gui.mainWindow
import cockpit.gui.mosaic.canvas
import cockpit.gui.mosaic.window as mosaic
import cockpit.util.userConfig
from cockpit import depot, events
from cockpit.gui.camera.viewPanel import ViewPanel
from cockpit.gui.device import EnableButton
from cockpit.gui.dialogs.experiment import singleSiteExperiment
from cockpit.gui.macroStage.macroStageXY import GoToXYZDialog, MacroStageXY
from cockpit.gui.macroStage.macroStageZ import MacroStageZ
from cockpit.gui.safeControls import EVT_SAFE_CONTROL_COMMIT, SetPointGauge
from cockpit.interfaces import stageMover
from cockpit.util.colors import wavelengthToColor


_VIEWPANEL_SIZE = wx.Size(250, 250)

_SITE_COLOURS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}

(
    VarCtrlContCmdEvt,
    EVT_VAR_CTRL_CONT_COMMAND_EVENT,
) = wx.lib.newevent.NewCommandEvent()


class MouseEventFilter(wx.EventFilter):
    def __init__(self, tlp, callback):
        super().__init__()
        self._tlp = tlp
        self._callback = callback
        self._exceptions = set()

    def FilterEvent(self, e):
        if (
            e.GetEventType() == wx.EVT_LEFT_DOWN.typeId
            and e.GetEventObject().GetTopLevelParent() == self._tlp
            and e.GetEventObject() not in self._exceptions
        ):
            self._callback(e)
            return self.Event_Processed
        else:
            return self.Event_Skip

    def add_exception(self, obj):
        self._exceptions.add(obj)


class IconButton(wx.ToggleButton):
    def __init__(
        self,
        parent,
        icon,
        callback,
        toggleable=False,
        icon_pressed=None,
        helptext="",
        rows=1,
        cols=1,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.icon = icon
        self.icon_pressed = icon_pressed
        self.callback = callback
        self.toggleable = toggleable
        self.helptext = helptext
        self._rows = rows
        self._cols = cols
        self.timer = wx.Timer(self)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        self.SetMinSize(wx.Size(self._cols * 48, self._rows * 48))
        image = wx.Image(os.path.join(cockpit.gui.IMAGES_PATH, self.icon))
        self.SetBitmap(image.ConvertToBitmap())
        if self.icon_pressed:
            image = wx.Image(
                os.path.join(cockpit.gui.IMAGES_PATH, self.icon_pressed)
            )
            self.SetBitmapPressed(image.ConvertToBitmap())
        self.Bind(wx.EVT_TOGGLEBUTTON, lambda e: self._visual_feedback(e))
        self.Bind(wx.EVT_TIMER, lambda e: self._on_timer(e))

    def _do_layout(self):
        pass

    def _visual_feedback(self, e):
        self.timer.StartOnce(500)
        self.callback(e)

    def _on_timer(self, e):
        if not self.toggleable:
            self.SetValue(False)


class ActionsPanel(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._sel_obj = None
        self._sel_cam = None
        self._sel_mar = None
        self._mouse_event_filter = MouseEventFilter(
            self.GetTopLevelParent(), self._cb_help_evt
        )
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Objective choice
        sizer_obj = wx.BoxSizer(wx.HORIZONTAL)
        sizer_obj.Add(
            wx.StaticText(self, label="Objective:", size=wx.Size(90, -1)),
            0,
            wx.ALIGN_CENTER,
        )
        self._sel_obj = wx.Choice(
            self, choices=wx.GetApp().Objectives.GetNamesSorted()
        )
        sizer_obj.Add(self._sel_obj, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
        self._sel_obj.Bind(
            wx.EVT_CHOICE,
            lambda e: wx.GetApp().Objectives.ChangeObjective(e.GetString()),
        )
        wx.GetApp().Objectives.Bind(
            cockpit.interfaces.EVT_OBJECTIVE_CHANGED,
            lambda e: self._sel_obj.SetSelection(
                self._sel_obj.FindString(e.GetString())
            ),
        )
        self._sel_obj.SetSelection(
            self._sel_obj.FindString(wx.GetApp().Objectives.GetName())
        )
        sizer.Add(sizer_obj, 0, wx.EXPAND | wx.BOTTOM, 5)
        # Camera choice
        sizer_cam = wx.BoxSizer(wx.HORIZONTAL)
        sizer_cam.Add(
            wx.StaticText(self, label="Mosaic camera:", size=wx.Size(90, -1)),
            0,
            wx.ALIGN_CENTER,
        )
        self._sel_cam = wx.Choice(
            self,
            choices=[
                camera.name for camera in depot.getHandlersOfType(depot.CAMERA)
            ],
        )
        sizer_cam.Add(self._sel_cam, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
        self._sel_cam.Bind(wx.EVT_CHOICE, lambda e: print(e))
        # subscription
        self._sel_cam.SetSelection(0)
        sizer.Add(sizer_cam, 0, wx.EXPAND | wx.BOTTOM, 5)
        # Marker colour choice
        sizer_mar = wx.BoxSizer(wx.HORIZONTAL)
        sizer_mar.Add(
            wx.StaticText(self, label="Marker colour:", size=wx.Size(90, -1)),
            0,
            wx.ALIGN_CENTER,
        )
        self._sel_mar = wx.Choice(self, choices=list(_SITE_COLOURS.keys()))
        sizer_mar.Add(self._sel_mar, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
        self._sel_mar.SetSelection(0)
        sizer.Add(sizer_mar, 0, wx.EXPAND | wx.BOTTOM, 5)
        # Button grid
        sizer_grid = wx.GridBagSizer(vgap=3, hgap=3)
        sizer_grid.AddMany(
            (
                (
                    IconButton(
                        self,
                        "touchscreen/action_mosaic.png",
                        lambda e: self._cb_mosaic(e),
                        toggleable=True,
                        icon_pressed="touchscreen/action_mosaic.png",
                        helptext="Start the mosaic.",
                    ),
                    wx.GBPosition(0, 0),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_centre.png",
                        lambda e: self._cb_centre(e),
                        helptext="Centre the view on the crosshair.",
                    ),
                    wx.GBPosition(0, 1),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_erase.png",
                        lambda e: self._cb_erase(e),
                        toggleable=True,
                        helptext="Erase the tile pointed by the crosshair.",
                    ),
                    wx.GBPosition(0, 2),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_experiment.png",
                        lambda e: self._cb_experiment(e),
                        helptext="Setup and perform an experiment.",
                    ),
                    wx.GBPosition(0, 3),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_marker.png",
                        lambda e: self._cb_marker(e),
                        helptext="Place a marker.",
                    ),
                    wx.GBPosition(0, 4),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_snap.png",
                        lambda e: self._cb_snap(e),
                        helptext="Take an image with all active cameras.",
                    ),
                    wx.GBPosition(1, 0),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_live.png",
                        lambda e: self._cb_live(e),
                        toggleable=True,
                        helptext=(
                            "Start or stop continuous image capture with all"
                            " active cameras."
                        ),
                    ),
                    wx.GBPosition(1, 1),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_help.png",
                        lambda e: self._cb_help(e),
                        toggleable=True,
                        helptext="Show help.",
                    ),
                    wx.GBPosition(1, 2),
                    wx.GBSpan(1, 1),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/action_abort.png",
                        lambda e: self._cb_abort(e),
                        cols=2,
                        helptext="Abort the current action.",
                    ),
                    wx.GBPosition(1, 3),
                    wx.GBSpan(1, 2),
                    wx.ALIGN_CENTER,
                ),
            )
        )
        # Update the state of the Live button when the video mode is toggled
        events.subscribe(
            events.VIDEO_MODE_TOGGLE,
            lambda state: self.GetChildren()[12].SetValue(state),
        )
        sizer.Add(sizer_grid, 0, wx.ALIGN_CENTRE)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()

    def _cb_mosaic(self, e):
        button = e.GetEventObject()
        mosaic_panel = self.GetTopLevelParent().GetChildren()[3]
        if button.GetValue():
            # Pressed => start mosaic
            camera = depot.getHandlerWithName(
                self._sel_cam.GetString(self._sel_cam.GetSelection())
            )
            if camera.getIsEnabled():
                mosaic_panel.masterMosaic.camera = camera
                mosaic_panel.masterMosaic.toggleMosaic()
            else:
                button.SetValue(False)
                wx.MessageBox(
                    "The %s camera is not enabled." % camera.descriptiveName,
                    caption='Selected camera is not active'
                )
        else:
            # Released => stop mosaic
            mosaic_panel.masterMosaic.shouldContinue.clear()

    def _cb_centre(self, e):
        mosaic_panel = self.GetTopLevelParent().GetChildren()[3]
        mosaic_panel.centerCanvas()

    def _cb_erase(self, e):
        button = e.GetEventObject()
        mosaic_panel = self.GetTopLevelParent().GetChildren()[3]
        if button.GetValue():
            # Pressed => enable deleting of tiles
            mosaic_panel.setSelectFunc(
                mosaic_panel.canvas.deleteTilesIntersecting
            )
        else:
            # Released => disable deleting of tiles
            mosaic_panel.setSelectFunc(None)

    def _cb_experiment(self, e):
        singleSiteExperiment.showDialog(self.GetTopLevelParent())

    def _cb_marker(self, e):
        colour = self._sel_mar.GetStringSelection()
        mosaic.window.saveSite(_SITE_COLOURS[colour])

    def _cb_snap(self, e):
        # Check that there is at least one camera and one light source active
        cams = depot.getActiveCameras()
        lights = [
            light
            for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE)
            if light.getIsEnabled()
        ]
        if not cams or not lights:
            print("Snap needs a light and a camera to opperate")
            return
        # Find the name of the active (first) camera
        camera_name = cams[0].name
        # Take the image
        events.executeAndWaitFor(
            events.NEW_IMAGE % camera_name,
            wx.GetApp().Imager.takeImage,
            shouldStopVideo=False,
        )
        mosaic.transferCameraImage()

    def _cb_live(self, e):
        button = e.GetEventObject()
        # Check that there is at least one camera and one light source active
        cams = depot.getActiveCameras()
        lights = [
            light
            for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE)
            if light.getIsEnabled()
        ]
        if not cams or not lights:
            print("Live needs a light and a camera to opperate")
            return
        # Find the name of the active (first) camera
        camera_name = cams[0].name
        # Toggle the video mode
        wx.GetApp().Imager.videoMode()
        if button.GetValue():
            # Pressed => transfer new images when they arrive
            events.subscribe(
                events.NEW_IMAGE % camera_name,
                lambda *args, **kwargs: mosaic.transferCameraImage(),
            )
        else:
            # Released => stop the transfer of images
            events.unsubscribe(
                events.NEW_IMAGE % camera_name,
                lambda *args, **kwargs: mosaic.transferCameraImage(),
            )

    def _cb_help(self, e):
        toggled = e.GetEventObject().GetValue()
        if toggled:
            self.GetTopLevelParent().SetCursor(
                wx.Cursor(wx.CURSOR_QUESTION_ARROW)
            )
            self._mouse_event_filter.add_exception(e.GetEventObject())
            wx.App.AddFilter(self._mouse_event_filter)
        else:
            self.GetTopLevelParent().SetCursor(wx.NullCursor)
            wx.App.RemoveFilter(self._mouse_event_filter)

    def _cb_help_evt(self, e):
        if e.GetEventObject().helptext:
            wx.TipWindow(e.GetEventObject(), e.GetEventObject().helptext)

    def _cb_abort(self, e):
        events.publish(events.USER_ABORT)
        # Untoggle Mosaic and Live buttons
        button_mosaic = self.GetChildren()[6]
        if button_mosaic.GetValue():
            button_mosaic.SetValue(False)
        button_live = self.GetChildren()[12]
        if button_live.GetValue():
            button_live.SetValue(False)


class VariableControlContinuous(wx.Panel):
    def __init__(
        self,
        parent,
        step_scale=1,
        step_offset=0,
        init_val=0,
        units="",
        limit_low=None,
        limit_high=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._step_scale = step_scale
        self._step_offset = step_offset
        self._value = init_val
        self._units = units
        self._limit_low = limit_low
        self._limit_high = limit_high
        self._but0 = None
        self._but1 = None
        self._txtctrl = None
        self._txt = None
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        # Minus button
        img_minus = wx.Image(
            os.path.join(cockpit.gui.IMAGES_PATH, "touchscreen/misc_minus.png")
        )
        self._but0 = wx.Button(self, size=wx.Size(24, 24))
        self._but0.SetBitmap(img_minus.ConvertToBitmap())
        self._but0.Bind(wx.EVT_BUTTON, lambda e: self._step(False))
        # Plus button
        img_plus = wx.Image(
            os.path.join(cockpit.gui.IMAGES_PATH, "touchscreen/misc_plus.png")
        )
        self._but1 = wx.Button(self, size=wx.Size(24, 24))
        self._but1.SetBitmap(img_plus.ConvertToBitmap())
        self._but1.Bind(wx.EVT_BUTTON, lambda e: self._step(True))
        # Text controls
        self._txtctrl = wx.TextCtrl(
            self, style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER
        )
        self._txtctrl.Bind(
            wx.EVT_TEXT_ENTER, lambda e: self.set_value(float(e.GetString()))
        )
        self._txtctrl.Bind(wx.EVT_KILL_FOCUS, self._on_focus_kill)
        self._txt = wx.StaticText(self, label=self._units)
        self._update_label()
        # Disable buttons if necessary
        if self._value == self._limit_low:
            self._but0.Disable()
        if self._value == self._limit_high:
            self._but1.Disable()
        # Layout
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._but0, 0, wx.ALIGN_CENTRE)
        sizer.Add(self._txtctrl, 1, wx.ALIGN_CENTRE | wx.LEFT, 5)
        sizer.Add(self._txt, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
        sizer.Add(self._but1, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
        self.SetSizer(sizer)
        self.Layout()

    def _step(self, direction):
        # Calculate the new value
        sign = direction * 2 - 1  # Bool -> {-1, 1}
        new_value = (
            self._value * pow(self._step_scale, sign)
            + sign * self._step_offset
        )
        # Saturate the new value and disable the associated button if necessary
        if self._limit_low is not None:
            if new_value <= self._limit_low:
                new_value = self._limit_low
                self._but0.Disable()
            else:
                self._but0.Enable()
        if self._limit_high is not None:
            if new_value >= self._limit_high:
                new_value = self._limit_high
                self._but1.Disable()
            else:
                self._but1.Enable()
        # Update value and post event if the value changed
        if self._value != new_value:
            self.set_value(new_value)
            evt = VarCtrlContCmdEvt(wx.ID_ANY)
            evt.SetEventObject(self)
            evt.SetClientData((direction, new_value))
            wx.PostEvent(self, evt)

    def _update_label(self):
        self._txtctrl.SetValue("{:.05G}".format(self._value))
        self.Refresh()

    def _on_focus_kill(self, e):
        self._update_label()
        e.Skip()

    def set_value(self, new_value):
        # Update value and label
        self._value = new_value
        self._update_label()


class LightsPanelEntry(wx.Panel):
    def __init__(self, parent, light_handler, power_handler=None, **kwargs):
        # Add style before initialisation
        if "style" in kwargs:
            kwargs["style"] |= wx.BORDER_RAISED
        else:
            kwargs["style"] = wx.BORDER_RAISED
        super().__init__(parent, **kwargs)
        self.light = light_handler
        self.power = power_handler
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # First row: wavelength bitmap and a toggle button
        sizer_row0 = wx.BoxSizer(wx.HORIZONTAL)
        img = wx.Image(
            os.path.join(
                cockpit.gui.IMAGES_PATH, "touchscreen/misc_wavelength.png",
            )
        )
        if self.power:
            img.Replace(
                255, 255, 255, *wavelengthToColor(self.power.wavelength)
            )
        sizer_row0.Add(
            wx.StaticBitmap(self, bitmap=img.ConvertToBitmap()),
            0,
            wx.ALIGN_CENTER,
        )
        button_toggle = EnableButton(self, self.light)
        button_toggle.setState(self.light.state)
        sizer_row0.Add(button_toggle, 1, wx.EXPAND | wx.LEFT, 5)
        sizer.Add(sizer_row0, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        # Second row: exposure control
        sizer_row1 = wx.BoxSizer(wx.HORIZONTAL)
        exposure_img = wx.Image(
            os.path.join(cockpit.gui.IMAGES_PATH, "touchscreen/misc_pulse.png")
        )
        exposure_ctrl = VariableControlContinuous(
            self, init_val=100, step_scale=1.2, units="ms", limit_low=1
        )
        exposure_ctrl.Bind(
            EVT_VAR_CTRL_CONT_COMMAND_EVENT,
            lambda e: self.light.setExposureTime(e.GetClientData()[1]),
        )
        self.light.addWatch("exposureTime", exposure_ctrl.set_value)
        sizer_row1.Add(
            wx.StaticBitmap(self, bitmap=exposure_img.ConvertToBitmap()),
            0,
            wx.ALIGN_CENTER,
        )
        sizer_row1.Add(exposure_ctrl, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
        sizer.Add(sizer_row1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        # Third row: power control
        if self.power:
            sizer_row2 = wx.BoxSizer(wx.VERTICAL)
            # Upper subrow
            sizer_row2_row0 = wx.BoxSizer(wx.HORIZONTAL)
            power_img = wx.Image(
                os.path.join(
                    cockpit.gui.IMAGES_PATH, "touchscreen/misc_power.png"
                )
            )
            power_ctrl = VariableControlContinuous(
                self,
                init_val=self.power.powerSetPoint * 100,
                step_offset=1,
                units="% ",
                limit_low=0,
                limit_high=100,
            )
            power_ctrl.Bind(
                EVT_VAR_CTRL_CONT_COMMAND_EVENT,
                lambda e: self.power.setPower(e.GetClientData()[1] / 100),
            )
            self.power.addWatch(
                "powerSetPoint", lambda x: power_ctrl.set_value(x * 100)
            )
            sizer_row2_row0.Add(
                wx.StaticBitmap(self, bitmap=power_img.ConvertToBitmap()),
                0,
                wx.ALIGN_CENTER,
            )
            sizer_row2_row0.Add(power_ctrl, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
            sizer_row2.Add(sizer_row2_row0, 0, wx.EXPAND)
            # Lower subrow
            sizer_row2_row1 = wx.BoxSizer(wx.HORIZONTAL)
            slider = SetPointGauge(
                self,
                minValue=0,
                maxValue=100,
                fetch_current=lambda: self.power.getPower() * 100,
                margins=wx.Size(3, 3),
                style=wx.BORDER_SIMPLE,
            )
            slider.Bind(
                EVT_SAFE_CONTROL_COMMIT,
                lambda e: self.power.setPower(e.Value / 100),
            )
            slider.SetValue(self.power.powerSetPoint * 100)
            self.power.addWatch(
                "powerSetPoint", lambda x: slider.SetValue(x * 100)
            )
            sizer_row2_row1.Add(24, 24, 0)
            sizer_row2_row1.Add(slider, 1, wx.ALIGN_CENTER | wx.LEFT, 24)
            sizer_row2_row1.Add(24, 24, 0)
            sizer_row2.Add(sizer_row2_row1, 0, wx.EXPAND)
            sizer.Add(
                sizer_row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5
            )
        sizer.Add(-1, 5, 0)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()


class LightsPanel(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Scrolled panel controls
        spanel = wx.lib.scrolledpanel.ScrolledPanel(self)
        sizer_spanel = wx.BoxSizer(wx.VERTICAL)
        lightToggleHandlers = sorted(
            depot.getHandlersOfType(depot.LIGHT_TOGGLE),
            key=lambda l: l.wavelength,
        )
        lightPowerHandlers = depot.getHandlersOfType(depot.LIGHT_POWER)
        for index, light_handler in enumerate(lightToggleHandlers):
            power_handler = next(
                filter(
                    lambda p: p.groupName == light_handler.groupName,
                    lightPowerHandlers,
                ),
                None,
            )
            if index < len(lightToggleHandlers) - 1:
                sizer_spanel.Add(
                    LightsPanelEntry(spanel, light_handler, power_handler),
                    0,
                    wx.EXPAND | wx.BOTTOM,
                    5,
                )
            else:
                sizer_spanel.Add(
                    LightsPanelEntry(spanel, light_handler, power_handler),
                    0,
                    wx.EXPAND,
                )
        spanel.SetSizer(sizer_spanel)
        sizer.Add(spanel, 1, wx.EXPAND)
        # Finalise the layout
        self.SetSizer(sizer)
        spanel.SetupScrolling()
        self.Layout()


class CamerasPanelEntry(wx.Panel):
    def __init__(self, parent, camera_handler, **kwargs):
        # Add style before initialisation
        if "style" in kwargs:
            kwargs["style"] |= wx.BORDER_RAISED
        else:
            kwargs["style"] = wx.BORDER_RAISED
        super().__init__(parent, **kwargs)
        self.camera_handler = camera_handler
        self.camera = depot.getDeviceWithName(camera_handler.name)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # First row: bitmap, and toggle button
        sizer_row0 = wx.BoxSizer(wx.HORIZONTAL)
        img = wx.Image(
            os.path.join(
                cockpit.gui.IMAGES_PATH, "touchscreen/misc_wavelength.png",
            )
        )
        if self.camera_handler.wavelength:
            img.Replace(255, 255, 255, *self.camera_handler.color)
        sizer_row0.Add(
            wx.StaticBitmap(self, bitmap=img.ConvertToBitmap()),
            0,
            wx.ALIGN_CENTER,
        )
        button_toggle = EnableButton(self, self.camera_handler)
        button_toggle.setState(self.camera_handler.state)
        sizer_row0.Add(button_toggle, 1, wx.EXPAND | wx.LEFT, 5)
        sizer.Add(sizer_row0, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        # Second row: gain
        if "gain" in self.camera.settings:
            sizer_row1 = wx.BoxSizer(wx.HORIZONTAL)
            gain_min, gain_max = self.camera.describe_setting("gain")["values"]
            gain_img = wx.Image(
                os.path.join(
                    cockpit.gui.IMAGES_PATH, "touchscreen/misc_opamp.png"
                )
            )
            gain_ctrl = VariableControlContinuous(
                self,
                init_val=self.camera.settings["gain"],
                step_offset=1,
                units="",
                limit_low=gain_min,
                limit_high=gain_max,
            )
            gain_ctrl.Bind(
                EVT_VAR_CTRL_CONT_COMMAND_EVENT,
                lambda e: self.camera.updateSettings(
                    {"gain": e.GetClientData()[1]}
                ),
            )
            events.subscribe(
                events.SETTINGS_CHANGED % self.camera,
                lambda: gain_ctrl.set_value(self.camera.settings["gain"]),
            )
            sizer_row1.Add(
                wx.StaticBitmap(self, bitmap=gain_img.ConvertToBitmap()),
                0,
                wx.ALIGN_CENTER,
            )
            sizer_row1.Add(gain_ctrl, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
            sizer.Add(
                sizer_row1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5
            )
        # Third row: readout and settings
        sizer_row2 = wx.BoxSizer(wx.HORIZONTAL)
        readout_choice = wx.Choice(self, choices=[])
        if "readout mode" in self.camera.settings:
            readout_choice.SetItems(self.camera._modenames)
            readout_choice.SetSelection(0)
        else:
            readout_choice.Enable(False)
        sizer_row2.Add(readout_choice, 1, wx.ALIGN_CENTER)
        button_settings = wx.Button(self, label="Settings")
        button_settings.Bind(wx.EVT_LEFT_UP, self.camera.showSettings)
        sizer_row2.Add(button_settings, 1, wx.ALIGN_CENTER | wx.LEFT, 5)
        sizer.Add(sizer_row2, 0, wx.EXPAND | wx.ALL, 5)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()


class CamerasPanel(wx.lib.scrolledpanel.ScrolledPanel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._current_camera_id = 0
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        cameraHandlers = depot.getHandlersOfType(depot.CAMERA)
        for index, camera_handler in enumerate(cameraHandlers):
            if index < len(cameraHandlers) - 1:
                sizer.Add(
                    CamerasPanelEntry(self, camera_handler),
                    0,
                    wx.EXPAND | wx.BOTTOM,
                    10,
                )
            else:
                sizer.Add(
                    CamerasPanelEntry(self, camera_handler), 0, wx.EXPAND
                )
        self.SetSizer(sizer)
        self.SetupScrolling()
        self.Layout()


class MenuColumn(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer_main = wx.BoxSizer(wx.VERTICAL)
        # Lights and camera selection
        splitter_window = wx.SplitterWindow(self)
        sizer_main.Add(splitter_window, 1, wx.EXPAND | wx.ALL, 5)
        ## Light selection
        lights_panel = wx.Panel(splitter_window)
        lights_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        lights_panel_staticboxsizer = wx.StaticBoxSizer(
            wx.VERTICAL, lights_panel, "Lights..."
        )
        lights_panel_staticboxsizer.Add(
            LightsPanel(lights_panel_staticboxsizer.GetStaticBox()),
            1,
            wx.EXPAND,
        )
        lights_panel_sizer.Add(lights_panel_staticboxsizer, 1, wx.EXPAND)
        lights_panel.SetSizer(lights_panel_sizer)
        ## Camera selection
        cameras_panel = wx.Panel(splitter_window)
        cameras_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        cameras_panel_staticboxsizer = wx.StaticBoxSizer(
            wx.VERTICAL, cameras_panel, "Camera..."
        )
        cameras_panel_staticboxsizer.Add(
            CamerasPanel(cameras_panel_staticboxsizer.GetStaticBox()),
            1,
            wx.EXPAND,
        )
        cameras_panel_sizer.Add(cameras_panel_staticboxsizer, 1, wx.EXPAND)
        cameras_panel.SetSizer(cameras_panel_sizer)
        # Finish configuration of splitter window
        splitter_window.SplitHorizontally(lights_panel, cameras_panel)
        splitter_window.SetSashGravity(0.5)
        # Actions
        sizer_actions = wx.StaticBoxSizer(wx.VERTICAL, self, "ACTION!")
        sizer_actions.Add(ActionsPanel(self), 0, wx.TOP, 5)
        sizer_main.Add(sizer_actions, 0, wx.EXPAND | wx.ALL, 5)
        # Finalise layout
        self.SetSizer(sizer_main)
        self.Layout()


class MosaicPanel(wx.Panel, mosaic.MosaicCommon):
    @property
    def selectedSites(self):
        return mosaic.window.selectedSites

    @property
    def primitives(self):
        return mosaic.window.primitives

    @property
    def focalPlaneParams(self):
        return mosaic.window.focalPlaneParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.masterMosaic = mosaic.window
        # MOSAIC ATTRIBUTES
        #     Last known location of the mouse.
        self.prevMousePos = None
        #     Last click position of the mouse.
        self.lastClickPos = None
        #     Function to call when tiles are selected.
        self.selectTilesFunc = None
        #     Size of the box to draw at the center of the crosshairs.
        self.crosshairBoxSize = 0

        # MOSAIC FONT ATTRIBUTES
        self.site_face = cockpit.gui.freetype.Face(self, 64)
        self.scale_face = cockpit.gui.freetype.Face(self, 18)
        # MORE MOSAIC ATTRIBUTES
        self.scalebar = cockpit.util.userConfig.getValue(
            "mosaicScaleBar", default=0
        )
        # Layout stuff
        sizer = wx.BoxSizer(wx.VERTICAL)
        limits = stageMover.getHardLimits()[:2]
        self.canvas = cockpit.gui.mosaic.canvas.MosaicCanvas(
            self, limits, self.drawOverlay, self.onMouse
        )
        sizer.Add(self.canvas, 1, wx.EXPAND)
        self.SetSizer(sizer)
        # self.Layout()
        self.SetBackgroundColour(wx.Colour(255, 0, 0))
        self.SetMinSize(wx.Size(600, -1))
        # MOSAIC BINDING
        events.subscribe(events.STAGE_POSITION, self.onAxisRefresh)
        events.subscribe("stage step size", self.onAxisRefresh)
        events.subscribe("soft safety limit", self.onAxisRefresh)
        events.subscribe("objective change", self.onObjectiveChange)
        events.subscribe("mosaic start", self.mosaicStart)
        events.subscribe("mosaic stop", self.mosaicStop)
        events.subscribe(events.MOSAIC_UPDATE, self.mosaicUpdate)
        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        for item in [self, self.canvas]:
            cockpit.gui.keyboard.setKeyboardHandlers(item)

    def Refresh(self, *args, **kwargs):
        """Refresh, with explicit refresh of glCanvases on Mac.
        Refresh is supposed to be called recursively on child objects,
        but is not always called for our glCanvases on the Mac. This may
        be due to the canvases not having any invalid regions, but I see
        no way to invalidate a region on demand."""
        super().Refresh(*args, **kwargs)
        if sys.platform == "darwin":
            wx.CallAfter(self.canvas.Refresh)
            macro_xy = (
                self.GetTopLevelParent()
                .GetChildren()[1]
                .GetChildren()[0]
                .GetChildren()[0]
            )
            macro_z = (
                self.GetTopLevelParent()
                .GetChildren()[1]
                .GetChildren()[1]
                .GetChildren()[0]
            )
            wx.CallAfter(macro_xy.Refresh)
            wx.CallAfter(macro_z.Refresh)

    def centerCanvas(self, event=None):
        curPosition = stageMover.getPosition()[:2]

        # Calculate the size of the box at the center of the crosshairs.
        # \todo Should we necessarily assume a 512x512 area here?
        # if we havent previously set crosshairBoxSize (maybe no camera active)
        if self.crosshairBoxSize == 0:
            self.crosshairBoxSize = 512 * wx.GetApp().Objectives.GetPixelSize()
        self.offset = wx.GetApp().Objectives.GetOffset()
        scale = 150.0 / self.crosshairBoxSize
        self.canvas.zoomTo(
            -curPosition[0] + self.offset[0],
            curPosition[1] - self.offset[1],
            scale,
        )

    def onSize(self, event):
        # Resize the canvas
        # TODO: Why set the client size of the panel directly? Is there no way
        # for the canvas to automatically get the size of the panel (i.e. its
        # parent)? It defeats the entire purpose of having sizers.
        csize = self.GetClientSize()
        self.canvas.SetClientSize((csize[0], csize[1]))
        self.SetClientSize((csize[0], csize[1]))

    def onAxisRefresh(self, axis, *args):
        # Get updated about new stage position info or step size.
        # This requires redrawing the display, if the axis is the X or Y axes.
        if axis in [0, 1]:
            # Only care about the X and Y axes.
            wx.CallAfter(self.Refresh)

    def onObjectiveChange(self, handler):
        # User changed the objective in use; resize our crosshair box to suit
        self.crosshairBoxSize = 512 * handler.pixel_size
        self.offset = handler.offset
        # force a redraw so that the crosshairs are properly sized
        self.Refresh()

    def onMouse(self, event):
        if self.prevMousePos is None:
            # We can't perform some operations without having a prior mouse
            # position, so if it doesn't exist yet, we short-circuit the
            # function. Normally we'll set this at the end of the function.
            self.prevMousePos = event.GetPosition()
            return

        mousePos = event.GetPosition()
        if event.LeftDown() or event.LeftDClick():
            self.lastClickPos = event.GetPosition()
        elif event.LeftUp() and self.selectTilesFunc is not None:
            # Call the specified function with the given range.
            start = self.canvas.mapScreenToCanvas(self.lastClickPos)
            end = self.canvas.mapScreenToCanvas(self.prevMousePos)
            self.selectTilesFunc((-start[0], start[1]), (-end[0], end[1]))
            self.lastClickPos = None
            self.Refresh()
        # Skip all other inputs while we select tiles.
        if self.selectTilesFunc is None:
            if event.LeftDClick():
                # Double left-click; move to the target position.
                currentTarget = self.canvas.mapScreenToCanvas(mousePos)
                newTarget = (
                    currentTarget[0] + self.offset[0],
                    currentTarget[1] + self.offset[1],
                )
                # stop mosaic if we are already running one
                if mosaic.window.amGeneratingMosaic:
                    self.masterMosaic.onAbort(mosaic.window)
                self.goTo(newTarget)
            elif event.LeftIsDown() and not event.LeftDown():
                # Dragging the mouse with the left mouse button: drag or
                # zoom, as appropriate.
                delta = (
                    mousePos[0] - self.prevMousePos[0],
                    mousePos[1] - self.prevMousePos[1],
                )
                if event.ShiftDown():
                    # Use the vertical component of mouse motion to zoom.
                    zoomFactor = 1 - delta[1] / 100.0
                    self.canvas.multiplyZoom(zoomFactor)
                else:
                    self.canvas.dragView(delta)
            elif event.GetWheelRotation():
                # Adjust zoom, based on the zoom rate.
                delta = event.GetWheelRotation()
                multiplier = 1.002
                if delta < 0:
                    # Invert the scaling direction.
                    multiplier = 2 - multiplier
                    delta *= -1
                self.canvas.multiplyZoom(multiplier ** delta)

        self.prevMousePos = mousePos

        if self.selectTilesFunc is not None:
            # Need to draw the box the user is drawing.
            self.Refresh()

        # HACK: switch focus to the canvas away from our listbox, otherwise
        # it will seize all future scrolling events.
        if self.GetParent().IsActive():
            self.canvas.SetFocus()

    def togglescalebar(self):
        # toggle the scale bar between 0 and 1.
        if self.scalebar != 0:
            self.scalebar = 0
        else:
            self.scalebar = 1
        # store current state for future.
        cockpit.util.userConfig.setValue("mosaicScaleBar", self.scalebar)
        self.Refresh()

    def mosaicStart(self):
        button_mosaic = (
            self.GetTopLevelParent()
            .GetChildren()[2]
            .GetChildren()[2]
            .GetChildren()[6]
        )
        # If the button is not pressed already then press it
        if not button_mosaic.GetValue():
            button_mosaic.SetValue(True)

    def mosaicStop(self):
        button_mosaic = (
            self.GetTopLevelParent()
            .GetChildren()[2]
            .GetChildren()[2]
            .GetChildren()[6]
        )
        # If the button is not released already then release it
        if button_mosaic.GetValue():
            button_mosaic.SetValue(False)

    def mosaicUpdate(self):
        self.Refresh()

    def setSelectFunc(self, func):
        self.selectTilesFunc = func
        self.lastClickPos = None


class StageControlXY(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Pose control
        sizer_pose = wx.BoxSizer(wx.HORIZONTAL)
        sizer_pose.Add(
            wx.StaticText(self, label="Position:"), 0, wx.ALIGN_CENTRE
        )
        pose_stxt = wx.StaticText(self, label="(99999, 99999)")
        cockpit.gui.EvtEmitter(self, cockpit.events.STAGE_POSITION).Bind(
            cockpit.gui.EVT_COCKPIT,
            lambda e: pose_stxt.SetLabel(
                "({:5.2f}, {:5.2f})".format(*stageMover.getPosition()[:2])
            ),
        )
        sizer_pose.Add(pose_stxt, 1, wx.ALIGN_CENTRE | wx.LEFT, 5)
        sizer.Add(sizer_pose, 0, wx.EXPAND | wx.TOP, 10)
        # Step controls
        ## x
        sizer_step_x = wx.BoxSizer(wx.HORIZONTAL)
        sizer_step_x.Add(
            wx.StaticText(self, label="X step:"), 0, wx.ALIGN_CENTRE
        )
        varctrl_step_x = VariableControlContinuous(
            self,
            init_val=wx.GetApp().Stage.GetStepSizes()[0],
            step_scale=5,
            units="um",
        )
        # TODO: Use stageMover.changeStepSize but modify it
        # to allow specifying an axis instead of changing all of them at the
        # same time
        varctrl_step_x.Bind(
            EVT_VAR_CTRL_CONT_COMMAND_EVENT,
            lambda e: wx.GetApp().Stage.SetStepSize(0, e.GetClientData()[1]),
        )
        cockpit.gui.EvtEmitter(self, "stage step size").Bind(
            cockpit.gui.EVT_COCKPIT,
            lambda e: varctrl_step_x.set_value(e.EventData[1])
            if e.EventData[0] == 0
            else e.Skip(),
        )
        sizer_step_x.Add(varctrl_step_x, 1, wx.LEFT, 5)
        ## y
        sizer_step_y = wx.BoxSizer(wx.HORIZONTAL)
        sizer_step_y.Add(
            wx.StaticText(self, label="Y step:"), 0, wx.ALIGN_CENTRE
        )
        varctrl_step_y = VariableControlContinuous(
            self,
            init_val=wx.GetApp().Stage.GetStepSizes()[1],
            step_scale=5,
            units="um",
        )
        varctrl_step_y.Bind(
            EVT_VAR_CTRL_CONT_COMMAND_EVENT,
            lambda e: wx.GetApp().Stage.SetStepSize(1, e.GetClientData()[1]),
        )
        cockpit.gui.EvtEmitter(self, "stage step size").Bind(
            cockpit.gui.EVT_COCKPIT,
            lambda e: varctrl_step_y.set_value(e.EventData[1])
            if e.EventData[0] == 1
            else e.Skip(),
        )
        sizer_step_y.Add(varctrl_step_y, 1, wx.LEFT, 5)
        ## common
        sizer.Add(sizer_step_x, 0, wx.EXPAND | wx.TOP, 5)
        sizer.Add(sizer_step_y, 0, wx.EXPAND | wx.TOP, 5)
        # Buttons
        sizer_buttons = wx.GridSizer(5, wx.Size(3, 3))
        sizer_buttons.AddMany(
            (
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_left.png",
                        lambda e: self._cb_move_left(e),
                        helptext="Move one step left.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_up.png",
                        lambda e: self._cb_move_up(e),
                        helptext="Move one step up.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_down.png",
                        lambda e: self._cb_move_down(e),
                        helptext="Move one step down.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_right.png",
                        lambda e: self._cb_move_right(e),
                        helptext="Move one step right.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_tiles.png",
                        lambda e: self._cb_tiles(e),
                        helptext="Show mosaic tiles.",
                    ),
                    wx.ALIGN_CENTER,
                ),
            )
        )
        sizer.Add(sizer_buttons, 0, wx.EXPAND | wx.TOP, 5)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()

    def _cb_move_left(self, e):
        pose = stageMover.getPosition()[:2]
        step = wx.GetApp().Stage.GetStepSizes()[0]
        pose[0] += step
        stageMover.goToXY(pose)

    def _cb_move_up(self, e):
        pose = stageMover.getPosition()[:2]
        step = wx.GetApp().Stage.GetStepSizes()[1]
        pose[1] += step
        stageMover.goToXY(pose)

    def _cb_move_down(self, e):
        pose = stageMover.getPosition()[:2]
        step = wx.GetApp().Stage.GetStepSizes()[1]
        pose[1] -= step
        stageMover.goToXY(pose)

    def _cb_move_right(self, e):
        pose = stageMover.getPosition()[:2]
        step = wx.GetApp().Stage.GetStepSizes()[0]
        pose[0] -= step
        stageMover.goToXY(pose)

    def _cb_tiles(self, e):
        mosaic = self.GetPrevSibling()
        mosaic.shouldDrawMosaic = not mosaic.shouldDrawMosaic


class StageControlZ(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Step control
        sizer_step_z = wx.BoxSizer(wx.HORIZONTAL)
        sizer_step_z.Add(
            wx.StaticText(self, label="Z step:"), 0, wx.ALIGN_CENTRE
        )
        varctrl_step_z = VariableControlContinuous(
            self,
            init_val=wx.GetApp().Stage.GetStepSizes()[2],
            step_scale=5,
            units="um",
        )
        varctrl_step_z.Bind(
            EVT_VAR_CTRL_CONT_COMMAND_EVENT,
            lambda e: wx.GetApp().Stage.SetStepSize(2, e.GetClientData()[1]),
        )
        cockpit.gui.EvtEmitter(self, "stage step size").Bind(
            cockpit.gui.EVT_COCKPIT,
            lambda e: varctrl_step_z.set_value(e.EventData[1])
            if e.EventData[0] == 2
            else e.Skip(),
        )
        sizer_step_z.Add(varctrl_step_z, 1, wx.LEFT, 5)
        sizer.Add(sizer_step_z, 0, wx.EXPAND | wx.TOP, 10)
        # Buttons
        sizer_buttons = wx.GridSizer(5, wx.Size(3, 3))
        sizer_buttons.AddMany(
            (
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_up.png",
                        lambda e: self._cb_move_up(e),
                        helptext="Move one step up.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_save_top.png",
                        lambda e: self._cb_save_top(e),
                        helptext=(
                            "Save the current position as the top soft limit."
                        ),
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_top.png",
                        lambda e: self._cb_move_top(e),
                        helptext="Move to the top soft limit.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_centre.png",
                        lambda e: self._cb_move_centre(e),
                        helptext=(
                            "Move to the centre of the top and bottom"
                            " soft limits."
                        ),
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_recentre.png",
                        lambda e: self._cb_recentre(e),
                        helptext=(
                            "Recentre all fine stages and then move the course"
                            " stage so that the focus plane remains the same."
                        ),
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_down.png",
                        lambda e: self._cb_move_down(e),
                        helptext="Move one step down.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_save_bottom.png",
                        lambda e: self._cb_save_bottom(e),
                        helptext=(
                            "Save the current position as the bottom"
                            " soft limit."
                        ),
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move_bottom.png",
                        lambda e: self._cb_move_bottom(e),
                        helptext="Move to the bottom soft limit.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_touchdown.png",
                        lambda e: self._cb_touchdown(e),
                        helptext=(
                            "Move to the specimen position, as defined in the"
                            " configuration file."
                        ),
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_switch.png",
                        lambda e: self._cb_switch(e),
                        helptext="Switch to the next stage.",
                    ),
                    wx.ALIGN_CENTER,
                ),
            )
        )
        sizer.Add(sizer_buttons, 0, wx.EXPAND | wx.TOP, 5)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()

    def _cb_move_up(self, e):
        stageMover.goToZ(
            stageMover.getPosition()[2] + wx.GetApp().Stage.GetStepSizes()[2]
        )

    def _cb_save_top(self, e):
        wx.GetApp().Stage.SavedTop = stageMover.getPosition()[2]

    def _cb_move_top(self, e):
        stageMover.moveZCheckMoverLimits(wx.GetApp().Stage.SavedTop)

    def _cb_move_centre(self, e):
        bottom = wx.GetApp().Stage.SavedBottom
        top = wx.GetApp().Stage.SavedTop
        centre = bottom + (top - bottom) / 2.0
        stageMover.moveZCheckMoverLimits(centre)

    def _cb_recentre(self, e):
        stageMover.recenterFineMotion()

    def _cb_move_down(self, e):
        stageMover.goToZ(
            stageMover.getPosition()[2] - wx.GetApp().Stage.GetStepSizes()[2]
        )

    def _cb_save_bottom(self, e):
        wx.GetApp().Stage.SavedBottom = stageMover.getPosition()[2]

    def _cb_move_bottom(self, e):
        stageMover.moveZCheckMoverLimits(wx.GetApp().Stage.SavedBottom)

    def _cb_touchdown(self, e):
        stageMover.goToZ(
            wx.GetApp().Config["stage"].getfloat("slideTouchdownAltitude")
        )

    def _cb_switch(self, e):
        stageMover.changeMover()


class StageControlCommon(wx.Panel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.dialog_safeties = None
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        # Buttons
        sizer = wx.GridSizer(5, wx.Size(3, 3))
        sizer.AddMany(
            (
                (
                    IconButton(
                        self,
                        "touchscreen/stage_safeties.png",
                        lambda e: self._cb_safeties(e),
                        helptext="Change the XYZ soft limits.",
                    ),
                    wx.ALIGN_CENTER,
                ),
                (
                    IconButton(
                        self,
                        "touchscreen/stage_move.png",
                        lambda e: self._cb_move(e),
                        helptext="Move to a specific XYZ location.",
                    ),
                    wx.ALIGN_CENTER,
                ),
            )
        )
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()

    def _cb_safeties(self, e):
        if self.dialog_safeties is None:
            self.dialog_safeties = DialogSafeties(self)
        self.dialog_safeties.Show()

    def _cb_move(self, e):
        GoToXYZDialog(self.GetParent())


class MacroStagesPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        self.SetMinSize(wx.Size(275, -1))

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # XY stage
        sizer_stage_xy = wx.StaticBoxSizer(wx.VERTICAL, self, "XY stage")
        sizer_stage_xy.Add(
            MacroStageXY(
                sizer_stage_xy.GetStaticBox(), size=wx.Size(225, 150)
            ),
            0,
            wx.EXPAND,
        )
        sizer_stage_xy.Add(
            StageControlXY(sizer_stage_xy.GetStaticBox()), 0, wx.ALIGN_CENTRE
        )
        sizer.Add(sizer_stage_xy, 0, wx.EXPAND | wx.ALL, 5)
        # Z stage
        sizer_stage_z = wx.StaticBoxSizer(wx.VERTICAL, self, "Z stage")
        sizer_stage_z.Add(
            MacroStageZ(sizer_stage_z.GetStaticBox(), size=wx.Size(225, 225)),
            0,
            wx.EXPAND,
        )
        sizer_stage_z.Add(
            StageControlZ(sizer_stage_z.GetStaticBox()), 0, wx.ALIGN_CENTRE
        )
        sizer.Add(sizer_stage_z, 0, wx.EXPAND | wx.ALL, 5)
        # Common stage control
        sizer_stage_xyz = wx.StaticBoxSizer(
            wx.VERTICAL, self, "Common stage control"
        )
        sizer_stage_xyz.Add(
            StageControlCommon(sizer_stage_xyz.GetStaticBox()),
            0,
            wx.ALIGN_CENTRE,
        )
        sizer.Add(sizer_stage_xyz, 0, wx.EXPAND | wx.ALL, 5)
        # Finalise layout
        self.SetSizer(sizer)
        self.Layout()


class ImagePreviewPanel(wx.lib.scrolledpanel.ScrolledPanel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        self.SetMinClientSize(wx.Size(250, -1))
        # Subscribe to all camera new image events
        # for camera in depot.getHandlersOfType(depot.CAMERA):
        #    # Subscribe to new image events only after canvas is prepared.
        #    events.subscribe("new image %s" % camera.name, self._on_new_image)
        events.subscribe(events.CAMERA_ENABLE, self.onCameraEnableEvent)

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Add a viewPanel for every camera
        for camera in depot.getHandlersOfType(depot.CAMERA):
            vpanel = ViewPanel(self)
            vpanel.change_size(_VIEWPANEL_SIZE)
            sizer.Add(vpanel)
        self.SetSizer(sizer)
        self.SetupScrolling(scroll_x=False)
        self.Layout()
        self.resetGrid()

    def _on_new_image(self, *args, **kwargs):
        print(
            "Received a new image, {:d} args and {:d} kwargs!".format(
                len(args), len(kwargs)
            )
        )

    @cockpit.util.threads.callInMainThread
    def onCameraEnableEvent(self, camera, enabled):
        views = [
            child
            for child in self.GetChildren()
            if isinstance(child, ViewPanel)
        ]
        activeViews = [view for view in views if view.getIsEnabled()]
        if enabled and camera not in [view.curCamera for view in activeViews]:
            inactiveViews = set(views).difference(activeViews)
            inactiveView = inactiveViews.pop()
            inactiveView.enable(camera)
            inactiveView.change_size(_VIEWPANEL_SIZE)
        elif not enabled:
            for view in activeViews:
                if view.curCamera is camera:
                    view.disable()
        self.resetGrid()

    def resetGrid(self):
        viewsToShow = []
        views = [
            child
            for child in self.GetChildren()
            if isinstance(child, ViewPanel)
        ]
        for view in views:
            view.Hide()
            if view.getIsEnabled():
                viewsToShow.append(view)
        # If there are no active views then display one empty panel.
        if not viewsToShow:
            viewsToShow.append(views[0])

        self.GetSizer().Clear()
        for view in viewsToShow:
            self.GetSizer().Add(view)
        self.GetSizer().ShowItems(True)

        self.GetSizer().Layout()
        self.SetSizer(self.GetSizer())
        self.SetupScrolling(scroll_x=False)
        # self.SetClientSize(self.panel.GetSize())
        self.Layout()

        # If enough views have been added for a scrollbar to appear,
        # review their widths to make them fit
        if (
            self.HasScrollbar(wx.VERTICAL) and self.GetClientSize()[0] > 1
        ):  # avoid this path during initialisation when the client
            # size is still 1x1
            new_width = self.GetClientSize()[0]
            vp_aspect_ratio = _VIEWPANEL_SIZE[0] / _VIEWPANEL_SIZE[1]
            new_height = new_width / vp_aspect_ratio
            for view in viewsToShow:
                view.change_size(wx.Size(new_width, new_height))


class DialogSafeties(wx.Dialog):
    def __init__(self, parent, **kwargs):
        kwargs["title"] = "Set stages' soft limits"
        self._scrollbars = []
        self._textctrls = []
        super().__init__(parent, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        pass

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Add controls
        for axis_index, axis_label in enumerate(("X", "Y", "Z")):
            for limit_index, limit_label in enumerate(("min", "max")):
                # Boundaries
                limits_hard = stageMover.getHardLimitsForAxis(axis_index)
                limits_soft = stageMover.getSoftLimitsForAxis(axis_index)
                # Widgets
                scrollbar = wx.ScrollBar(self, size=wx.Size(256, 32))
                scrollbar.SetScrollbar(
                    limits_soft[limit_index],
                    0,
                    limits_hard[1] - limits_hard[0],
                    100,
                )
                textctrl = wx.TextCtrl(
                    self,
                    size=wx.Size(64, -1),
                    value="{:g}".format(limits_soft[limit_index]),
                    style=wx.TE_CENTRE | wx.TE_PROCESS_ENTER,
                )
                self._scrollbars.append(scrollbar)
                self._textctrls.append(textctrl)
                # Event handling
                scrollbar.Bind(
                    wx.EVT_SCROLL,
                    lambda e, tc=textctrl: tc.SetValue(
                        "{:g}".format(e.GetPosition())
                    ),
                )
                textctrl.Bind(
                    wx.EVT_TEXT_ENTER,
                    lambda e, sb=scrollbar: self._update_scrollbar(
                        sb, int(e.GetString())
                    ),
                )
                textctrl.Bind(
                    wx.EVT_KILL_FOCUS,
                    lambda e, sb=scrollbar: self._on_focus_kill(
                        sb, int(e.GetString())
                    ),
                )
                # Sizing
                sizer_row = wx.BoxSizer(wx.HORIZONTAL)
                sizer_row.Add(
                    wx.StaticText(
                        self, label="{:s} {:s}".format(axis_label, limit_label)
                    ),
                    0,
                    wx.ALIGN_CENTRE,
                )
                sizer_row.Add(scrollbar, 1, wx.ALIGN_CENTRE | wx.LEFT, 5)
                sizer_row.Add(textctrl, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
                sizer_row.Add(
                    wx.StaticText(self, label="um"),
                    0,
                    wx.ALIGN_CENTER | wx.LEFT,
                    5,
                )
                sizer.Add(
                    sizer_row, 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, 5
                )
        # Buttons
        sizer.Add(
            wx.StaticLine(self), 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, 10
        )
        sizer_row_buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_close = wx.Button(self, label="Close")
        button_close.Bind(wx.EVT_BUTTON, lambda e: self._on_close(e))
        button_apply = wx.Button(self, label="Apply")
        button_apply.Bind(wx.EVT_BUTTON, lambda e: self._on_apply(e))
        sizer_row_buttons.Add(button_close, 0, wx.ALIGN_CENTRE)
        sizer_row_buttons.Add(button_apply, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
        sizer.Add(
            sizer_row_buttons, 0, wx.ALIGN_CENTRE | wx.TOP | wx.BOTTOM, 5
        )
        # Further event handling
        cockpit.gui.EvtEmitter(self, "soft safety limit").Bind(
            cockpit.gui.EVT_COCKPIT, lambda e: self._on_limit_soft_change(e)
        )
        # Finalise layout
        self.SetSizer(sizer)
        self.DoLayoutAdaptation()

    def _update_scrollbar(self, scrollbar, value):
        scrollbar.SetPosition(value)

    def _on_focus_kill(self, scrollbar, value):
        self._update_scrollbar(scrollbar, value)

    def _on_close(self, e):
        self.Close()

    def _on_apply(self, e):
        # Verify that the ranges make sense
        makeSense = True
        values = [sb.GetThumbPosition() for sb in self._scrollbars]
        for axis_index, (min, max) in enumerate(
            zip(values[::2], values[1::2])
        ):
            if min > max:
                makeSense = False
                print(
                    "Mismatch between minimum and maximum limits for axis",
                    ("X", "Y", "Z")[axis_index],
                )
                break
        if makeSense:
            # Set the limits all at once
            for axis_index, (min, max) in enumerate(
                zip(values[::2], values[1::2])
            ):
                stageMover.setSoftMin(axis_index, min)
                stageMover.setSoftMax(axis_index, max)
            # Close the dialog
            self.Close()

    def _on_limit_soft_change(self, e):
        # Unpack event data
        axis, value, isMax = e.EventData[:3]
        # Update both respective scrollbar and textctrl
        index = axis * 2 + int(isMax)
        self._scrollbars[index].SetThumbPosition(value)
        self._textctrls[index].SetValue("{:g}".format(value))


class TouchScreenWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_properties()
        self._do_layout()

    def _set_properties(self):
        self.SetStatusBar(cockpit.gui.mainWindow.StatusLights(parent=self))

    def _do_layout(self):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(MacroStagesPanel(self), 0, wx.EXPAND)
        sizer.Add(MenuColumn(self), 0, wx.EXPAND)
        sizer.Add(MosaicPanel(self), 1, wx.EXPAND)
        sizer.Add(ImagePreviewPanel(self), 0, wx.EXPAND)
        self.SetSizerAndFit(sizer)
        self.Layout()
        # Recentre the mosaic
        self.GetChildren()[3].centerCanvas()


def makeWindow(parent):
    TouchScreenWindow(parent, title="Touch Screen view")
