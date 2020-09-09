#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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


## This module serves as a central coordination point for all devices. Devices
# are initialized and registered from here, and if a part of the UI wants to 
# interact with a specific kind of device, they can find it through the depot.

import collections
import configparser
import os

from cockpit.handlers.deviceHandler import DeviceHandler

## Different eligible device handler types. These correspond 1-to-1 to
# subclasses of the DeviceHandler class.
CAMERA = "camera"
DRAWER = "drawer"
EXECUTOR = "experiment executor"
GENERIC_DEVICE = "generic device"
GENERIC_POSITIONER = "generic positioner"
IMAGER = "imager"
LIGHT_FILTER = "light filter"
LIGHT_POWER = "light power"
LIGHT_TOGGLE = "light source"
OBJECTIVE = "objective"
POWER_CONTROL = "power control"
SERVER = "server"
STAGE_POSITIONER = "stage positioner"

SKIP_CONFIG = ['server']

class DeviceDepot:
    ## Initialize the Depot.
    def __init__(self):
        ## Maps config section names to device
        self.nameToDevice = {}
        ## Maps devices to their handlers.
        self.deviceToHandlers = {}
        ## Maps handlers back to their devices.
        self.handlerToDevice = {}
        ## List of all device handlers for active modules.
        self.handlersList = []
        ## Maps handler device types to lists of the handlers controlling that
        # type.
        self.deviceTypeToHandlers = collections.defaultdict(list)
        ## Maps handler names to handlers with those names. NB we enforce that
        # there only be one handler per name when we load the handlers.
        self.nameToHandler = {}
        ## Maps group name to handlers.
        self.groupNameToHandlers = collections.defaultdict(list)


    ## Call the initialize() method for each registered device, then get
    # the device's Handler instances and insert them into our various
    # containers.  Yield the device names as we go.
    def initialize(self, config):
        ## TODO: we will want to remove this print statements when
        ## we're done refactoring the location of the log and config
        ## files (issue #320)
        print("Cockpit is running from %s" % os.path.split(os.path.abspath(__file__))[0])

        # Create our server
        from cockpit.devices.server import CockpitServer

        ## TODO remove special case by having fallback empty section?
        ## Or fallback to the defaults in the class?
        if config.has_section('server'):
            sconf = dict(config.items('server'))
        else:
            sconf = {}
        self.nameToDevice['server'] = CockpitServer('server', sconf)


        # Parse config to create device instances.
        for name in config.sections():
            if name in SKIP_CONFIG:
                continue
            try:
                cls = config.gettype(name, 'type')
            except configparser.NoOptionError:
                raise RuntimeError("Missing 'type' key for device '%s'" % name)

            device_config = dict(config.items(name))
            try:
                device = cls(name, device_config)
            except Exception as e:
                raise RuntimeError("Failed to construct device '%s'" % name, e)
            self.nameToDevice[name] = device

        # Initialize devices in order of dependence
        # Convert to list - python3 dict_values has no pop method.
        devices = list(self.nameToDevice.values())
        done = []
        while devices:
            # TODO - catch circular dependencies.
            d = devices.pop(0)
            depends = []
            for dependency in ['triggersource', 'analogsource', 'controller']:
                other = d.config.get(dependency)
                if other:
                    if other not in self.nameToDevice:
                        raise Exception("Device %s depends on non-existent device '%s'." %
                                        (d.name, other))
                    depends.append(other)

            if any([other not in done for other in depends]):
                devices.append(d)
                continue
            yield d.name
            self.initDevice(d)
            done.append(d.name)

        # Add dummy devices as required.
        dummies = []

        # Dummy objectives
        if not getHandlersOfType(OBJECTIVE):
            from cockpit.devices.objective import ObjectiveDevice
            dummy_obj_config = {
                "40x": {
                    "pixel_size": "0.2",
                    "offset": "(-100, 50, 0)",
                },
                "60xWater": {
                    "pixel_size": "0.1",
                },
                "60xOil": {
                    "pixel_size": "0.1",
                },
                "100xOil": {
                    "pixel_size": "0.08",
                },
                "150xTIRF": {
                    "pixel_size": "0.06",
                },
            }
            for obj_name, obj_config in dummy_obj_config.items():
                dummies.append(ObjectiveDevice(obj_name, obj_config))

        # Dummy stages
        axes = self.getSortedStageMovers().keys()
        if 2 not in axes:
            from cockpit.devices.dummies import DummyStage
            dummies.append(DummyStage("dummy Z stage",
                                      {"z-lower-limits": "0",
                                       "z-upper-limits": "2500",
                                       "z-units-per-micron": "1"}))

        if (0 not in axes) or (1 not in axes):
            from cockpit.devices.dummies import DummyStage
            dummies.append(DummyStage("dummy XY stage",
                                      {"x-lower-limits": "0",
                                       "x-upper-limits": "25000",
                                       "x-units-per-micron": "1",
                                       "y-lower-limits": "0",
                                       "y-upper-limits": "12000",
                                       "y-units-per-micron": "1"}))

        # Cameras
        if not getHandlersOfType(CAMERA):
            from cockpit.devices.dummies import DummyCamera
            for i in range(1, 5):
                dummies.append(DummyCamera('Dummy camera %d' % i, {}))
        # Dummy imager
        if not getHandlersOfType(IMAGER):
            from cockpit.devices.dummies import DummyDSP
            dummies.append(DummyDSP('imager', {}))
        # Dummy laser
        if not getHandlersOfType(LIGHT_TOGGLE):
            from cockpit.devices.dummies import DummyLaser
            for wl in [405, 488, 633]:
                dummies.append(DummyLaser('Dummy %d' % wl, {'wavelength' : wl}))
        # Initialise dummies.
        for d in dummies:
            self.nameToDevice[d.name] = d
            self.initDevice(d)

        self.finalizeInitialization()
        yield 'dummy-devices'


    def addHandler(self, handler, device=None):
        self.deviceTypeToHandlers[handler.deviceType].append(handler)
        if handler.name in self.nameToHandler:
            # We enforce unique names, but multiple devices may reference
            # the same handler, e.g. where a device A is triggered by signals
            # from device B, device B provides the handler that generates the
            # signals, and device A will reference that handler.
            otherHandler = self.nameToHandler[handler.name]
            if handler is not otherHandler:
                otherDevice = self.handlerToDevice[otherHandler]
                raise RuntimeError("Multiple handlers with the same name [%s] from devices [%s] and [%s]" %
                                   (handler.name, str(device), str(otherDevice)))
        self.nameToHandler[handler.name] = handler
        self.handlerToDevice[handler] = device
        self.groupNameToHandlers[handler.groupName].append(handler)


    ## Initialize a Device.
    def initDevice(self, device):
        device.initialize()
        device.performSubscriptions()

        handlers = device.getHandlers()
        if not handlers:
            # device is not used
            return
        self.deviceToHandlers[device] = handlers
        self.handlersList.extend(handlers)
        for handler in handlers:
            self.addHandler(handler, device)

    ## Let each device publish any initial events it needs. It's assumed this
    # is called after all the handlers have set up their UIs, so that they can
    # be adjusted to match the current configuration. 
    def makeInitialPublications(self):
        for device in self.nameToDevice.values():
            device.makeInitialPublications()
        for handler in self.handlersList:
            handler.makeInitialPublications()


    ## Do any extra initialization needed now that everything is properly
    # set up.
    def finalizeInitialization(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
           for device in self.nameToDevice.values():
               pool.submit(device.finalizeInitialization)
        # Context manager ensures devices are finalized before handlers.
        with ThreadPoolExecutor(max_workers=4) as pool:
            for handler in self.handlersList:
                pool.submit(handler.finalizeInitialization)


    ## Return a mapping of axis to a sorted list of positioners for that axis.
    # We sort by range of motion, with the largest range coming first in the
    # list.
    def getSortedStageMovers(self):
        axisToMovers = {}
        for mover in self.deviceTypeToHandlers[STAGE_POSITIONER]:
            if mover.axis not in axisToMovers:
                axisToMovers[mover.axis] = []
            axisToMovers[mover.axis].append(mover)

        for axis, handlers in axisToMovers.items():
            handlers.sort(reverse = True,
                    key = lambda a: a.getHardLimits()[1] - a.getHardLimits()[0]
            )
        return axisToMovers



## XXX: Global singleton
deviceDepot = None


## Simple passthrough.
def initialize(config):
    global deviceDepot
    deviceDepot = DeviceDepot()
    for device in deviceDepot.initialize(config):
        yield device


## Simple passthrough.
def makeInitialPublications():
    deviceDepot.makeInitialPublications()


## Return the handler with the specified name.
def getHandlerWithName(name):
    return deviceDepot.nameToHandler.get(name, None)


## Return all registered device handlers of the appropriate type.
def getHandlersOfType(deviceType):
    return deviceDepot.deviceTypeToHandlers[deviceType]


## Return all registered device handlers in the appropriate group.
def getHandlersInGroup(groupName):
    return deviceDepot.groupNameToHandlers[groupName]


## Get all registered device handlers.
def getAllHandlers():
    return deviceDepot.nameToHandler.values()


## Get all registered devices.
def getAllDevices():
    return deviceDepot.nameToDevice.values()


## Simple passthrough.
def getSortedStageMovers():
    return deviceDepot.getSortedStageMovers()


## Get all cameras that are currently in use.
def getActiveCameras():
    cameras = getHandlersOfType(CAMERA)
    result = []
    for camera in cameras:
        if camera.getIsEnabled():
            result.append(camera)
    return result


## Add a handler
def addHandler(handler, device=None):
    return deviceDepot.addHandler(handler, device)

## Get a device by its name.
def getDeviceWithName(name):
    return deviceDepot.nameToDevice.get(name)


## Get the handlers of a specific type for a device.
def getHandler(nameOrDevice, handlerType):
    if isinstance(nameOrDevice, DeviceHandler):
        if nameOrDevice.deviceType == handlerType:
            return nameOrDevice
    if isinstance(nameOrDevice, str):
        dev = getDeviceWithName(nameOrDevice)
    else:
        dev = nameOrDevice

    handlers = set(getHandlersOfType(handlerType))
    devHandlers = set(deviceDepot.deviceToHandlers.get(dev, []))
    handlers = handlers.intersection(devHandlers)
    if len(handlers) == 0:
        return None
    elif len(handlers) == 1:
        return handlers.pop()
    else:
        return list(handlers)
