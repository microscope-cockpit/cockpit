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

"""Device handlers are the interface between UI and Cockpit devices.

Device handlers are the primary way that Cockpit devices communicates
with the UI and vice versa.  Each handler represents an abstracted
*component* of a device and not simply a type of device.  For example,
an XY stage device provides two handlers, one per axis.  A laser
device also provides two handlers, a light source handler and a light
power handler: the light source handler controls the light source
state --- on or off --- while the light power handler controls its
intensity.

Cockpit automatically builds its user interface based on the handlers
provided by all available devices.  After initialising devices, depot
collects all handlers via the device ``getHandlers()`` method.

Each ``DeviceHandler`` has different defined functions, e.g., a
``PositionerHandler`` has ``moveRelative()`` and ``moveAbsolute()``.
These methods in turn invoke callback functions specified by the
Cockpit device itself which then presumably talks to the hardware.
For information on the required and optional callbacks for each
handler check their source code.

In short, Cockpit talks to a devide handler, the device handler talks
a Cockpit device, and a Cockpit device talks to the hardware.

Historical reasons
==================

This package makes most sense if we consider that Cockpit has its own
device specific code.  However, this is now mostly handled by `Python
Microscope <https://python-microscope.org>`__ which provides all
devices under a standard interface.  This suggests that if all
hardware is handled by Python Microscope we should be able to remove
the devices and handlers abstraction layers.

"""
