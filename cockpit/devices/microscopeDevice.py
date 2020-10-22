#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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


"""Microscope devices.

   Supports devices that implement the interface defined in
   microscope.devices

For a direct connection::

    [device]
    type: cockpit.devices.a_module.SomeClass
    uri: PYRO:SomeDevice@host.port

For connection via a controller::

    [device]
    type: cockpit.devices.a_module.SomeClass
    controller: some_controller
    controller.name: remote_device    # optional

    [some_controller]
    type: cockpit.devices.another_module.AnotherClass
    uri: PYRO:SomeControler@host.port

"""

import typing

import Pyro4
import wx
from cockpit import events
from cockpit.devices import device
from cockpit import depot
import cockpit.gui.device
import cockpit.handlers.deviceHandler
import cockpit.handlers.filterHandler
import cockpit.handlers.lightPower
import cockpit.handlers.lightSource
import cockpit.util.colors
import cockpit.util.userConfig
import cockpit.util.threads
from cockpit.gui.device import SettingsEditor
from cockpit.handlers.stagePositioner import PositionerHandler
from cockpit.interfaces import stageMover
import re
from microscope.devices import AxisLimits

# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

class MicroscopeBase(device.Device):
    """A class to communicate with the UniversalDevice interface."""
    def __init__(self, name, config):
        super().__init__(name, config)
        self.handlers = []
        self.panel = None
        # Pyro proxy
        self._proxy = None
        self.settings = {}
        self.cached_settings={}
        self.settings_editor = None
        self.defaults = DEFAULTS_NONE
        self.enabled = True
        # Placeholders for methods deferred to proxy.
        self.get_all_settings = None
        self.get_setting = None
        self.set_setting = None
        self.describe_setting = None
        self.describe_settings = None

    def initialize(self):
        super().initialize()
        # Connect to the proxy.
        if 'controller' not in self.config:
            self._proxy = Pyro4.Proxy(self.uri)
        else:
            c = depot.getDeviceWithName(self.config['controller'])
            c_name = self.config.get('controller.name', None)
            if c_name is not None:
                try:
                    self._proxy = c._proxy.devices[c_name]
                except:
                    raise Exception("%s: device not found on controller '%s'." % (self.name, c.name))
            elif len(c._proxy.devices) == 0:
                raise Exception("%s: no devices found on controller." % self.name)
            elif len(c._proxy.devices) == 1:
                    self._proxy = next(iter(c._proxy.devices.values()))
            else:
                 raise Exception("%s: More than one device found on controller, "\
                                 "so must specify controller.name." % self.name)
        self.get_all_settings = self._proxy.get_all_settings
        self.get_setting = self._proxy.get_setting
        self.set_setting = self._proxy.set_setting
        self.describe_setting = self._proxy.describe_setting
        self.describe_settings = self._proxy.describe_settings

    def onExit(self) -> None:
        if self._proxy is not None:
            self._proxy._pyroRelease()
        super().onExit()

    def finalizeInitialization(self):
        super().finalizeInitialization()
        # Set default settings on remote device. These will be over-
        # ridden by any defaults in userConfig, later.
        # Currently, settings are an 'advanced' feature --- the remote
        # interface relies on us to send it valid data, so we have to
        # convert our strings to the appropriate type here.
        ss = self.config.get('settings')
        settings = {}
        if ss:
            settings.update(([m.groups() for kv in ss.split('\n')
                             for m in [re.match(r'(.*)\s*[:=]\s*(.*)', kv)] if m]))
        for k,v in settings.items():
            try:
                desc = self.describe_setting(k)
            except:
                print ("%s ingoring unknown setting '%s'." % (self.name, k))
                continue
            if desc['type'] == 'str':
                pass
            elif desc['type'] == 'int':
                v = int(v)
            elif desc['type'] == 'float':
                v = float(v)
            elif desc['type'] == 'bool':
                v = v.lower() in ['1', 'true']
            elif desc['type'] == 'tuple':
                print ("%s ignoring tuple setting '%s' - not yet supported." % (self.name, k))
                continue
            elif desc['type'] == 'enum':
                if v.isdigit():
                    v = int(v)
                else:
                    vmap = dict((k,v) for v,k in desc['values'])
                    v = vmap.get(v, None)
                if v is None:
                    print ("%s ignoring enum setting '%s' with unrecognised value." % (self.name, k))
                    continue
            self.set_setting(k, v)
        self._readUserConfig()


    def getHandlers(self):
        """Return device handlers. Derived classes may override this."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    def showSettings(self, evt):
        if not self.settings_editor:
            # TODO - there's a problem with abstraction here. The settings
            # editor needs the describe/get/set settings functions from the
            # proxy, but it also needs to be able to invalidate the cache
            # on the handler. The handler should probably expose the
            # settings interface.
            self.setAnyDefaults()
            import collections.abc
            if self.handlers and isinstance(self.handlers, collections.abc.Sequence):
                h = self.handlers[0]
            elif self.handlers:
                h = self.handlers
            else:
                h = None
            parent = evt.EventObject.Parent
            self.settings_editor = SettingsEditor(self, parent, handler=h)
            self.settings_editor.Show()
        self.settings_editor.SetPosition(wx.GetMousePosition())
        self.settings_editor.Raise()


    def updateSettings(self, settings=None):
        if settings is not None:
            self._proxy.update_settings(settings)
        self.settings.update(self._proxy.get_all_settings())
        events.publish(events.SETTINGS_CHANGED % str(self))


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        if self.defaults != DEFAULTS_PENDING:
            # nothing to do
            return
        try:
            self._proxy.update_settings(self.settings)
        except Exception as e:
            print (e)
        else:
            self.defaults = DEFAULTS_SENT


    def _readUserConfig(self):
        idstr = self.name + '_SETTINGS'
        defaults = cockpit.util.userConfig.getValue(idstr)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.settings.update(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


class MicroscopeGenericDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


class MicroscopeSwitchableDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def finalizeInitialization(self):
        super().finalizeInitialization()
        self.enabled = self._proxy.get_is_enabled()


class MicroscopeLaser(MicroscopeBase):
    """A light source with power control.

    Sample config entry:
      [488nm]
      type: MicroscopeLaser
      uri: PYRO:DeepstarLaser@192.168.0.2:7001
      wavelength: 488
      triggerSource: trigsource
      triggerLine: 1

      [trigsource]
      type: ExecutorDevice
      ...
    """
    def _setEnabled(self, on):
        if on:
            self._proxy.enable()
        else:
            self._proxy.disable()

    def getHandlers(self):
        self.handlers.append(cockpit.handlers.lightPower.LightPowerHandler(
            self.name + ' power',  # name
            self.name + ' light source',  # groupName
            {
                'setPower': self._setPower,
                'getPower': self._getPower,
            },
            self.config.get('wavelength', None),
            curPower=.2,
            isEnabled=True))
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        self.handlers.append(cockpit.handlers.lightSource.LightHandler(
            self.name,
            self.name + ' light source',
            {'setEnabled': lambda name, on: self._setEnabled(on),
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime},
            self.config.get('wavelength', None),
            100,
            trighandler,
            trigline))

        return self.handlers


    @cockpit.util.threads.callInNewThread
    def _setPower(self, power: float) -> None:
        self._proxy.power = power

    def _getPower(self) -> float:
        return self._proxy.power


    def finalizeInitialization(self):
        # This should probably work the other way around:
        # after init, the handlers should query for the current state,
        # rather than the device pushing state info to the handlers as
        # we currently do here.
        ph = self.handlers[0] # powerhandler
        ph.powerSetPoint = self._proxy.get_set_power()
        # Set lightHandler to enabled if light source is on.
        lh = self.handlers[-1]
        lh.state = int(self._proxy.get_is_on())


class MicroscopeFilter(MicroscopeBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cameras
        cdefs = self.config.get('cameras', None)
        if cdefs:
            self.cameras = re.split('[,;]\s*', cdefs)
        else:
            self.cameras = None

        # Lights
        ldefs = self.config.get('lights', None)
        if ldefs:
            self.lights = re.split('[,;]\s*', ldefs)
        else:
            self.lights = None

        # Filters
        fdefs = self.config.get('filters')
        if fdefs is None:
            raise Exception(
                "Missing 'filters' value for device '%s'" % self.name
            )
        fdefs = [re.split(':\s*|,\s*', f) for f in re.split('\n', fdefs) if f]
        self.filters = [cockpit.handlers.filterHandler.Filter(*f) for f in fdefs]


    def getHandlers(self):
        """Return device handlers."""
        h = cockpit.handlers.filterHandler.FilterHandler(self.name, 'filters', False,
                                                 {'setPosition': self.setPosition,
                                                  'getPosition': self.getPosition,
                                                  'getFilters': self.getFilters},
                                                 self.cameras,
                                                 self.lights)
        self.handlers = [h]
        return self.handlers


    def setPosition(self, position, callback=None):
        asproxy = Pyro4.Proxy(self._proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.set_setting('position', position).then(callback)


    def getPosition(self):
        return self._proxy.get_setting('position')


    def getFilters(self):
        return self.filters


class _MicroscopeStageAxis:
    """Wrap a Python microscope StageAxis for a cockpit PositionerHandler.

    Args:
        axis: an instance of `microscope.devices.StageAxis`.
        index: the cockpit axis index value for this axis (0 for X, 1
            for Y, or 2 for Z).
        units_per_micron: the number of units, or steps, used by the
            device per µm.
        stage_name: the name of the stage device, used to construct
            the handler name.
    """
    def __init__(self, axis, index: int, units_per_micron: float,
                 stage_name: str) -> None:
        self._axis = axis
        self._units_per_micron = units_per_micron
        self._name = "%d %s" % (index, stage_name)

        limits = AxisLimits(self._axis.limits.lower / self._units_per_micron,
                            self._axis.limits.upper / self._units_per_micron)

        group_name = "%d stage motion" % index
        eligible_for_experiments = False
        # TODO: to make it eligible for experiments, we need a
        # getMovementTime callback (see issue #614).
        callbacks = {
            'getMovementTime' : self.getMovementTime,
            'getPosition' : self.getPosition,
            'moveAbsolute' : self.moveAbsolute,
            'moveRelative' : self.moveRelative,
        }

        self._handler = PositionerHandler(self._name, group_name,
                                          eligible_for_experiments, callbacks,
                                          index, limits)

    def getHandler(self) -> PositionerHandler:
        return self._handler

    def getMovementTime(self, index: int, start: float, end: float) -> float:
        # TODO: this is not implemented yet but it shouldn't be called
        # anyway because we are not eligible for experiments.
        del index
        raise NotImplementedError('')

    def getPosition(self, index: int) -> float:
        """Get the position for the specified axis."""
        del index
        return self._axis.position / self._units_per_micron

    def moveAbsolute(self, index: int, position: float) -> None:
        """Move axis to the given position in microns."""
        # Currently, the move methods of a Python Microscope stage
        # blocks until the move is done.  When there is an async move
        # stage on Microscope, we don't have to block here and can
        # send STAGE_MOVER events as the move happens and
        # STAGE_STOPPED when it is done (whatever that means).
        self._axis.move_to(position * self._units_per_micron)
        events.publish(events.STAGE_MOVER, index)
        events.publish(events.STAGE_STOPPED, self._name)

    def moveRelative(self, index: int, delta: float) -> None:
        """Move the axis by the specified delta, in microns."""
        # See comments on moveAbsolute about async moves.
        self._axis.move_by(delta * self._units_per_micron)
        events.publish(events.STAGE_MOVER, index)
        events.publish(events.STAGE_STOPPED, self._name)


class MicroscopeStage(MicroscopeBase):
    """Device class for a Python microscope StageDevice.

    This device requires two configurations per axis:

    1. The ``axis-name`` configuration specifies the name of the axis
       on the Python microscope ``StageDevice``.  Usually, this is
       something like ``X`` or ``Y`` but can be any string.  Refer to
       the device documentation.

    2. The ``units-per-micron`` configuration specifies the number of
       units, or steps, used by the device in a µm.  This value is
       used to convert between the device units into physical units.

    For example, a remote XY stage with 0.1µm steps, and a separate Z
    stage with 25nm steps, would have a configuration entry like so::

      [XY stage]
      type: cockpit.devices.microscopeDevice.MicroscopeStage
      uri: PYRO:SomeXYStage@192.168.0.2:7001
      x-axis-name: X
      y-axis-name: Y
      # Each step is 0.1µm, therefore 10 steps per µm
      x-units-per-micron: 10 # 1 step == 0.1µm
      y-units-per-micron: 10 # 1 step == 0.1µm

      [Z stage]
      type: cockpit.devices.microscopeDevice.MicroscopeStage
      uri: PYRO:SomeZStage@192.168.0.2:7002
      z-axis-name: Z
      # Each step is 25nm, therefore 40 steps per µm
      x-units-per-micron: 40

    """

    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        super().__init__(name, config)
        self._axes = [] # type: typing.List[_MicroscopeStageAxis]


    def initialize(self) -> None:
        super().initialize()

        # The names of the axiss we have already configured, to avoid
        # handling the same one under different names, and to ensure
        # that we have all axis configured.
        handled_axis_names = set()

        their_axes_map = self._proxy.axes
        for one_letter_name in 'xyz':
            axis_config_name = one_letter_name + '-axis-name'
            if axis_config_name not in self.config:
                # This stage does not have this axis.
                continue

            their_name = self.config[axis_config_name]
            if their_name not in their_axes_map:
                raise Exception('unknown axis named \'%s\'' % their_name)

            units_config_name = one_letter_name + '-units-per-micron'
            if units_config_name not in self.config:
                raise Exception('missing \'%s\' value in the configuration'
                                % units_config_name)
            units_per_micron = float(self.config[units_config_name])
            if units_per_micron <= 0.0:
                raise ValueError('\'%s\' configuration must be a positive value'
                                 % units_config_name)

            their_axis = their_axes_map[their_name]
            cockpit_index = stageMover.AXIS_MAP[one_letter_name]
            self._axes.append(_MicroscopeStageAxis(their_axis, cockpit_index,
                                                   units_per_micron, self.name))
            handled_axis_names.add(their_name)

        # Ensure that there isn't a non handled axis left behind.
        for their_axis_name in their_axes_map.keys():
            if their_axis_name not in handled_axis_names:
                # FIXME: maybe this should be a warning instead?  What
                # if this is a stage with more than XYZ axes and it's
                # not configured simply because cockpit can't handle
                # them?
                raise Exception('No configuration for the axis named \'%s\''
                                % their_axis_name)

        # Enabling the stage might cause it to move to home.  If it
        # has been enabled before, it might do nothing.  We have no
        # way to know.
        self._proxy.enable()


    def getHandlers(self) -> typing.List[PositionerHandler]:
        # Override MicroscopeBase.getHandlers.  Do not call super.
        return [x.getHandler() for x in self._axes]
