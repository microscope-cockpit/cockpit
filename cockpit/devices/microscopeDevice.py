#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
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
import time
from cockpit import events
from cockpit.devices import device
from cockpit import depot
import cockpit.gui.device
import cockpit.handlers.deviceHandler
import cockpit.handlers.filterHandler
import cockpit.handlers.lightPower
import cockpit.handlers.lightSource
import cockpit.handlers.digitalioHandler
import cockpit.util.colors
import cockpit.util.userConfig
import cockpit.util.threads
import cockpit.util.listener
import cockpit.util.logger
from cockpit.util import valueLogger
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
                             for m in [re.match(r'(.*?)\s*[:=]\s*(.*?)$', kv)] if m]))
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
        result = asproxy.set_position(position).then(callback)


    def getPosition(self):
        return self._proxy.get_position()


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

        if self._proxy.may_move_on_enable():
            # Motors will home during enable.
            title = "Stage needs to move"
            msg = (
                "The '%s' stage needs to find the home position."
                " Homing may move it so please ensure that there are"
                " no obstructions, then press 'OK' to home the stage."
                " If you press 'Cancel' the stage will not be homed"
                " and its behaviour will be unpredictable."
                % (self.name)
            )
            if cockpit.gui.guiUtils.getUserPermission(msg, title):
                 self._proxy.enable()
        else:
            self._proxy.enable()

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

    def getHandlers(self) -> typing.List[PositionerHandler]:
        # Override MicroscopeBase.getHandlers.  Do not call super.
        return [x.getHandler() for x in self._axes]

class MicroscopeDIO(MicroscopeBase):
    """Device class for asynchronous Digital Inout and Output signals.
    This class enables the configuration of named buttons in main GUI window
    to control for situation such a switchable excitation paths.

    Additionally it provides a debug window which allow control of the 
    state of all output lines and the direction (input or output) of each 
    control line assuming the hardware support this.
    """

    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        super().__init__(name, config)
        self.name = name

    def initialize(self) -> None:
        super().initialize()
        self.numLines=self._proxy.get_num_lines()
        #cache which we can read from if we dont want a roundtrip
        #to the remote.
        self._cache = [False]*self.numLines
        self.labels = [""]*self.numLines
        self.IOMap = [None]*self.numLines

        #read config entries if they exisit to
        iomapConfig = self.config.get('iomap',[None]*self.numLines)
        if iomapConfig[0] is not None:
            #config is deifned so read it into a bool variable,
            # else it is all [Nones]
            iomap=iomapConfig.split(',')
            for i,state in enumerate(iomap):
                self.IOMap[i]=bool(int(state))
        labels = self.config.get('labels',None)
        paths = self.config.get('paths',None)

        if self.IOMap[0] is not None:
            #first entry is not None so map defined
            self._proxy.set_all_IO_state(self.IOMap)
        else:
            #no map so set all lines to output
            self._proxy.set_all_IO_state([True]*self.numLines)
        #start all output lines as false
        for i in range(self.numLines):
            if self.IOMap[i]:
                self.write_line(i,False)
                
        ##extract names of lines from file, too many are ignored,
        ## too few are padded with str(line number)
        templabels=[]
        if labels:
            templabels=eval(labels)
        for i in range(self.numLines):
            if i<len(templabels):
                self.labels[i]=templabels[i]
            else:
                self.labels[i]=("Line %d" %i)
        # extract defined paths
        if paths:
            self.paths=eval(paths)
        else:
            self.paths={}
        # Lister to receive data back from hardware
        self.listener = cockpit.util.listener.Listener(self._proxy,
                                               lambda *args:
                                                       self.receiveData(*args))
        #log to record line state chnages
        self.logger = valueLogger.ValueLogger(self.name,
                    keys=self.labels)
        events.subscribe(events.DIO_INPUT,self.log_state_change)
        events.subscribe(events.DIO_OUTPUT,self.log_state_change)



    def read_line(self, line: int, cache=False, updateGUI=True) -> int:
        if cache:
            return self._cache[line]
        state = self._proxy.read_line(line)
        if updateGUI:
            #prevent a loop by calling this read line in the button
            #toggle code
            events.publish(events.DIO_INPUT,line,state)
        return state

    def read_all_lines(self, cache=False):
        if cache:
            return self._cache
        states=self._proxy.read_all_lines()
        for i in range(len(states)):
            events.publish(events.DIO_INPUT,i,states[i])
        return (states)

    def write_line(self, line: int, state: bool) -> None:
        self._proxy.write_line(line,state)
        events.publish(events.DIO_OUTPUT,line,state)

    def write_all_lines(self, array):
        self._proxy.write_all_lines(array)
        for i in range(len(array)):
            events.publish(events.DIO_OUTPUT,i,array[i])

    def get_IO_state(self,line, cache=False):
        if cache:
            return(self.IOMap[line])
        state=self._proxy.get_IO_state(line)
        self.IOMap[line] = state
        return(state)

    def set_IO_state(self,line,state):
        self.IOMap[line] = state
        self._proxy.set_IO_state(line,state)

    def enable(self,state):
        if state:
            self._proxy.enable()
            self.listener.connect()
            return(True)
        else:
            self._proxy.disable()
            self.listener.disconnect()
            return(False)

    def log_state_change(self,line,state):
        #log befroe we update cache to get sharp transitions.
        self.logger.log(list(map(int,self._cache)))
        self._cache[line]=state
        #need to map bool's to ints for valuelogviewer
        self.logger.log(list(map(int,self._cache)))

        
    ## Debugging function: display a debug window.
    def showDebugWindow(self):
        self.DIOdebugWindow=DIOOutputWindow(self, parent=wx.GetApp().GetTopWindow()).Show()

    def getHandlers(self):
        """Return device handlers."""
        ##nneds functions to get and set signals for save and load
        ##channel functionality. 
        h = cockpit.handlers.digitalioHandler.DigitalIOHandler(self.name,
                             'DIO', False, 
                            {'setOutputs': self.write_all_lines,
                             'setIOstate': self.set_IO_state,
                             'getOutputs': self.read_all_lines,
                             'getIOstate': self.get_IO_state,
                             'getPaths': self.getPaths,
                             'write line': self.write_line,
                             'get labels': self.getLabels,
                             'enable': self.enable})
        self.handlers = [h]
        return self.handlers

    def getLabels(self):
        return self.labels

    def getPaths(self):
        return self.paths

    def receiveData(self, *args):
        """This function is called when input line state is received from 
        the hardware."""
        ((line,state),timestamp) = args
        if self.IOMap[line]:
            #this is meant to be an output line!
            raise Exception('Input signal received on an output digital line')
        #State changed send event to interested parties.
        events.publish(events.DIO_INPUT,line,state)

## This debugging window lets each digital lineout of the DIO device
## be manipulated individually.

class DIOOutputWindow(wx.Frame):
    def __init__(self, DIO, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        ## piDevice instance.
        self.DIO = DIO
        # Contains all widgets.
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        toggleSizer = wx.GridSizer(1, DIO.numLines, 1, 1)
        buttonSizer = wx.GridSizer(1, DIO.numLines, 1, 1)

        ## Maps buttons to their lines.
        self.lineToButton = {}
        self.state=self.DIO._proxy.read_all_lines()
        # Set up the digital lineout buttons.
        for i in range(DIO.numLines) :
            #state of IO , output or Input
            toggle = wx.ToggleButton(panel, wx.ID_ANY)
            toggle.Bind(wx.EVT_TOGGLEBUTTON, lambda evt: self.updateState())
            toggleSizer.Add(toggle, 1, wx.EXPAND)
            ioState=self.DIO.get_IO_state(i)
            toggle.SetValue(ioState)
            if ioState:
                toggle.SetLabel("Output")
            else:
                toggle.SetLabel("Input")
            #Button to toggle state of output lines.
            button = wx.ToggleButton(panel, wx.ID_ANY, self.DIO.labels[i])
            button.Bind(wx.EVT_TOGGLEBUTTON, lambda evt: self.toggle())
            buttonSizer.Add(button, 1, wx.EXPAND)
            self.lineToButton[i] = [toggle,button]
            if (self.state[i] is not None):
                button.SetValue(bool(self.state[i]))
            else:
                #if no state reported from remote set to false
                button.SetValue(False)
            if (ioState==False):
                #need to do something like colour the button red
                button.Disable()
                button.SetLabel(str(int(self.DIO.read_line(i))))
            else:
                button.Enable()

        mainSizer.Add(toggleSizer)
        mainSizer.Add(buttonSizer)
        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())
        events.subscribe(events.DIO_OUTPUT,self.outputChanged)
        events.subscribe(events.DIO_INPUT,self.inputChanged)

    #functions to updated chaces and GUI displays when DIO state changes. 
    def outputChanged(self,line,state):
        #check this is an output line
        if self.DIO.IOMap:
            self.lineToButton[line][1].SetValue(state)
            self.updateState(line,bool(state))

    def inputChanged(self,line,state):
        self.updateState(line,bool(state))

    ## One of our buttons was clicked; update the debug output.
    def toggle(self):
        for line, (toggle, button)  in self.lineToButton.items():
            if (self.DIO.get_IO_state(line)):
                self.DIO.write_line(line, button.GetValue())
            else:
                #read input state.
                button.SetValue=bool(self.DIO.read_line(line,updateGUI=False))

    ## One of our buttons was clicked; update the debug output.
    @cockpit.util.threads.callInMainThread
    def updateState(self,line = None,state = None):
        if (line is not None) and (state is not None):
            cockpit.util.logger.log.debug("Line %d returned %s" %
                                          (line,str(state)))
            if (self.DIO.get_IO_state(line)):
                #output button have names
                self.lineToButton[line][1].SetLabel(self.DIO.labels[line])
            else:
                self.lineToButton[line][1].SetLabel(str(int(state)))
            return()
        for line, (toggle, button)  in self.lineToButton.items():
            state=toggle.GetValue()
            self.DIO.set_IO_state(line, state)
            if state:
                button.Enable()
                toggle.SetLabel("Output")
                button.SetLabel(self.DIO.labels[line])
            else:
                button.Disable()
                toggle.SetLabel("Input")
                state=self.DIO.read_line(line,updateGUI = False)
                button.SetLabel(str(int(state)))


class MicroscopeValueLogger(MicroscopeBase):
    """Device class for asynchronous Digital Inout and Output signals.
    This class enables the configuration of named buttons in main GUI window
    to control for situation such a switchable excitation paths.

    Additionally it provides a debug window which allow control of the 
    state of all output lines and the direction (input or output) of each 
    control line assuming the hardware support this.
    """

    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        super().__init__(name, config)
        self.name = name

    def initialize(self) -> None:
        super().initialize()
        self.numSensors=self._proxy.get_num_sensors()
        #cache which we can read from if we dont want a roundtrip
        #to the remote.
        self._cache = [False]*self.numSensors
        self.labels = [""]*self.numSensors
        labels = self.config.get('labels',None)
        ##extract names of lines from file, too many are ignored,
        ## too few are padded with str(line number)
        templabels=[]
        if labels:
            templabels=eval(labels)
        for i in range(self.numSensors):
            if i<len(templabels):
                self.labels[i]=templabels[i]
            else:
                self.labels[i]=("Sensor %d" %i)
        # Lister to receive data back from hardware
        self.listener = cockpit.util.listener.Listener(self._proxy,
                                               lambda *args:
                                                       self.receiveData(*args))
        #log to record line state chnages
        self.logger = valueLogger.ValueLogger(self.name,
                    keys=self.labels)
        self.enable(True)
        
    def receiveData(self, *args):
        """This function is called sensors return data from 
        the hardware."""
        (data,timestamp) = args
        events.publish(events.VALUELOGGER_INPUT,data)
        self.logger.log(data)
        


    def enable(self,state):
        if state:
            self._proxy.enable()
            self.listener.connect()
            return(True)
        else:
            self._proxy.disable()
            self.listener.disconnect()
            return(False)


