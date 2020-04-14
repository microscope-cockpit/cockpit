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
import microscope.testsuite.devices

import cockpit.devices.executorDevices
import cockpit.devices.microscopeCamera
import cockpit.devices.microscopeDevice


class _MicroscopeTestDevice:
    def __init__(self, test_device_cls, name: str,
                 config: typing.Mapping[str, str]):
        # Ideally, the Cockpit device class for Microscope devices
        # would simply take a microscope.Device instance (which could
        # be, or not, a Pyro proxy).  However, it really only works
        # with Pyro proxies so we must create a Pyro daemon for it.
        # We also can't use Microscope's device server for this
        # because it wasn't designed to be called from other programs.
        test_device = test_device_cls()
        test_device.initialize()
        pyro_daemon = Pyro4.Daemon()
        pyro_uri = pyro_daemon.register(test_device)
        self._pyro_thread = threading.Thread(target=pyro_daemon.requestLoop)
        self._pyro_thread.start()

        if 'uri' in config:
            raise Exception('a URI config value must not defined')
        config = config.copy()
        config['uri'] = pyro_uri
        super().__init__(name, config)


class DummyCamera(_MicroscopeTestDevice,
                  cockpit.devices.microscopeCamera.MicroscopeCamera):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.TestCamera,
                         *args, **kwargs)


class DummyDSP(_MicroscopeTestDevice,
               cockpit.devices.executorDevices.ExecutorDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.DummyDSP,
                         *args, **kwargs)


class DummyLaser(_MicroscopeTestDevice,
                 cockpit.devices.microscopeDevice.MicroscopeLaser):
    def __init__(self, *args, **kwargs):
        super().__init__(microscope.testsuite.devices.TestLaser,
                         *args, **kwargs)
