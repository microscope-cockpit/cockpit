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


class Device:
    """Base class for Cockpit devices.

    This serves as the base class for any Device subclass.  Devices
    are as close as Cockpit gets to speaking directly to hardware.
    Device implementation is largely left up to the client; this class
    simply provides a framework of stub functions that must be
    implemented.

    Args:
      name: name of the device.  In the depot configuration file this
          is the name of the section where the device is declared.
      config: map of the device configuration to their values as
          strings.  This is the key/values read from the device
          section on the depot configuration file.

    """
    _config_types = {
        'port': int,
    }


    # Define __lt__ to make handlers sortable.
    def __lt__(self, other):
        return self.name.lower() < other.name.lower()


    def __init__(self, name='', config={}):
        self.name = name
        self.config = config
        # Convert config strings to types specified on device class.
        for k, t in self._config_types.items():
            if k in self.config:
                self.config[k] = t(self.config[k])
        ip = config.get('ipaddress', False)
        if ip:
            self.ipAddress = ip
        port = config.get('port', False)
        if port:
            self.port = port
        uri = config.get('uri', False)
        if uri:
            self.uri = uri


    ## Perform any necessary initialization (e.g. connecting to hardware).
    def initialize(self):
        pass


    ## Generate a list of DeviceHandlers representing the various capabilities
    # we are responsible for. Each DeviceHandler represents an abstract bit
    # of hardware -- for example, a generic camera, or a stage mover along
    # a single axis, or a light source. Take a look at the 
    # "handlers/deviceHandler.py" file for more information.
    def getHandlers(self):
        return []


    ## Construct any special UI the Device needs. Most Devices will not need
    # to do anything here, but if you have settings that the user needs to be
    # able to manipulate and that the normal UI will not handle, then this 
    # is where you create your specific UI. 
    # \return a WX Sizer or Panel that will be inserted into the main controls
    #         window, or None if nothing is to be inserted. 
    def makeUI(self, parent):
        return None


    ## Subscribe to any events we care about.
    def performSubscriptions(self):
        pass


    ## Publish any needed information. This is called after all UI widgets
    # have been generated, so they are able to respond to these publications.
    def makeInitialPublications(self):
        pass


    ## Do any final actions needed, now that all of the devices are set up
    # and all initial publications and subscriptions have been made.
    def finalizeInitialization(self):
        pass

    def onExit(self) -> None:
        pass
