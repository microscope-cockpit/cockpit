#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

"""Device specific modules.

The `cockpit.devices` package is the closest in Cockpit to the
physical devices.  Most of these modules do not contact directly to
the devices but they connect to the device server/daemon/service that
does.  The depot configuration file typically refers to classes in
this package.  For example:

.. code:: ini

    [XY stage]
    type: cockpit.devices.microscopeDevice.MicroscopeStage
    uri: PYRO:SomeXYStage@192.168.0.2:7001
    ...

For the actual arguments required by each class, i.e., the key/values
required in the depot configuration file, see the individual Cockpit
device classes.

The primary task that Cockpit devices are responsible for is creation
of device handlers.  Each handler represents an abstract bit of
hardware, for example a camera or stage mover.  The ``getHandlers()``
function is expected to generate and return a list of handlers; the UI
then interacts with these handlers when the user performs actions.
See the :mod:`cockpit.handlers` package for details.

Some notable modules in this package are:

- :mod:`cockpit.devices.device` module with the base class for all
  Cockpit devices.

- :mod:`cockpit.devices.microscopeDevice` module with all Python
  Microscope adaptors excluding cameras.

- :mod:`cockpit.devices.microscopeCamera` module with the adaptor for
  Python Microscope cameras.

- :mod:`cockpit.devices.dummies` module with dummy devices for testing
  Cockpit.

- :mod:`cockpit.devices.server` module with the Cockpit server device,
  the server that other devices will connect to in order to send data
  to Cockpit.

- :mod:`cockpit.devices.executorDevices` module for the interaction
  with a trigger sources.


Historical details
==================

While support for new hardware is done via Microscope and used with
Microscope adaptors, historically Cockpit also handled the hardware
control itself.  Some hardware specific code is still part of Cockpit,
e.g., the ``picomotor`` and ``sr470`` modules, because support for
them has not yet been implemented in Microscope.

The long term plan is to have all device control handled in
Microscope.  When that happens, it may be that only Microscope
adaptors should be kept and they will no longer need to be referred as
adaptors since they will be the only ones.  At that time, the
separation between Cockpit devices and device handlers can probably be
removed.  We might also find that highly specialised devices will
continue to require a specialised Cockpit device class, such as the
Aurox Clarity, although maybe they will be better distributed as their
own Python package.

"""
