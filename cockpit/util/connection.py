#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Julio Mateos Langerak <julio.mateos-langerak@igh.cnrs.fr>
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


import Pyro4
from cockpit import depot

## Simple class for managing connections to remote services.
class Connection:
    def __init__(self, serviceName, ipAddress, port, localIp = None):
        ## Name of the service on the remote server.
        self.serviceName = serviceName
        ## IP address to connect to.
        self.ipAddress = ipAddress
        ## Port to connect to.
        self.port = port
        ## Local IP address to use for communication, in the event that this
        # computer has multiple networks to choose from.
        self.localIp = localIp
        ## Function to call when we get something from the camera.
        self.callback = None
        ## Extant connection to the camera.
        self.connection = None


    ## Establish a connection with the remote service, and tell
    # it to send us its data.
    # By default we set a short timeout of 5s so that we find out fairly
    # quickly if something went wrong.
    def connect(self, callback, timeout = 5):
        self.callback = callback
        connection = Pyro4.Proxy(
                'PYRO:%s@%s:%d' % (self.serviceName, self.ipAddress, self.port))
        connection._pyroTimeout = timeout
        self.connection = connection
        server = depot.getHandlersOfType(depot.SERVER)[0]
        uri = server.register(self.callback, self.localIp)
        self.connection.receiveClient(uri)


    ## Remove the connection and stop listening to the service.
    def disconnect(self):
        if self.connection is not None:
            server = depot.getHandlersOfType(depot.SERVER)[0]
            server.unregister(self.callback)
            try:
                self.connection.receiveClient(None)
            except Exception as e:
                print ("Couldn't disconnect from %s: %s" % (self.serviceName, e))
            self.connection = None
