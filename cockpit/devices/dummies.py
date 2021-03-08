#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import threading
import typing

import Pyro4
import microscope.devices
import microscope.testsuite.devices

import cockpit.devices.executorDevices
import cockpit.devices.microscopeCamera
import cockpit.devices.microscopeDevice
from cockpit.handlers.stagePositioner import PositionerHandler


class _MicroscopeTestDevice:
    def __init__(self, test_device: microscope.devices.Device,
                 name: str, config: typing.Mapping[str, str]) -> None:
        # Ideally, the Cockpit device class for Microscope devices
        # would simply take a microscope.Device instance (which could
        # be, or not, a Pyro proxy).  However, it really only works
        # with Pyro proxies so we must create a Pyro daemon for it.
        # We also can't use Microscope's device server for this
        # because it wasn't designed to be called from other programs.
        test_device.initialize()
        pyro_daemon = Pyro4.Daemon()
        pyro_uri = pyro_daemon.register(test_device)
        self._pyro_thread = threading.Thread(target=pyro_daemon.requestLoop,
                                             daemon=True)
        self._pyro_thread.start()

        if 'uri' in config:
            raise Exception('a dummy device must not have a uri config value'
                            ' but \'%s\' was given' % config['uri'])
        config = config.copy()
        config['uri'] = pyro_uri
        super().__init__(name, config)


class DummyCamera(_MicroscopeTestDevice,
                  cockpit.devices.microscopeCamera.MicroscopeCamera):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.TestCamera(),
                         *args, **kwargs)


class DummyDSP(_MicroscopeTestDevice,
               cockpit.devices.executorDevices.ExecutorDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.DummyDSP(),
                         *args, **kwargs)


class DummyLaser(_MicroscopeTestDevice,
                 cockpit.devices.microscopeDevice.MicroscopeLaser):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.TestLaser(),
                         *args, **kwargs)


class DummyStage(_MicroscopeTestDevice,
                 cockpit.devices.microscopeDevice.MicroscopeStage):
    """Dummy stages.

    This device requires the ``lower-limits``, ``upper-limits``, and
    ``units-per-micron`` configuration values for each axis to be
    created.  The first letter of the configuration defines the axis.
    For example, to create a dummy XY stage:

    .. config: ini

        [dummy XY stage]
        x-lower-limits: 0
        x-upper-limits: 25000
        x-units-per-micron: 1
        y-lower-limits: 0
        y-upper-limits: 12000
        y-units-per-micron: 1

    """
    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        limits = {} # type: typing.Dict[str, microscope.devices.AxisLimits]
        config = config.copy()
        for one_letter in 'xyz':
            lower_limits_key = one_letter + '-lower-limits'
            upper_limits_key = one_letter + '-upper-limits'
            units_per_micron_key = one_letter + '-units-per-micron'
            if lower_limits_key in config and upper_limits_key in config:
                if units_per_micron_key not in config:
                    Exception('no unites per micron config for \'%s\' axis'
                              % one_letter)
                lower_limits = float(config.pop(lower_limits_key))
                upper_limits = float(config.pop(upper_limits_key))
                limits[one_letter] = microscope.devices.AxisLimits(lower_limits,
                                                                   upper_limits)
                config[one_letter + '-axis-name'] = one_letter
            elif lower_limits_key in config or upper_limits_key in config:
                raise Exception('only one limit for the \'%s\' axis on config'
                                % one_letter)

        test_stage = microscope.testsuite.devices.TestStage(limits)
        super().__init__(test_stage, name, config)

    def getHandlers(self) -> typing.List[PositionerHandler]:
        handlers = super().getHandlers()
        for handler in handlers:
            # XXX: cockpit's MicroscopeStage device class does not
            # have getMovementTime yet (issue #614) so it can't be
            # used in experiments.  So we modify the handlers.
            handler.isEligibleForExperiments = True
            handler.callbacks['getMovementTime'] = lambda *args : (1, 1)
        return handlers
