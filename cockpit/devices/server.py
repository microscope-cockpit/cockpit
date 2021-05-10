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


import Pyro4
import threading
import traceback

from cockpit.devices import device
import cockpit.handlers.server
import cockpit.util.logger
import cockpit.util.threads


class CockpitServer(device.Device):
    """Cockpit server that accepts connections from remote devices.

    This Device represents the cockpit itself, and is mostly used to
    allow other computers to send information to the cockpit program.
    It handles selecting the ports that are used by these other
    devices, so that each incoming connection is on its own port.

    """
    def __init__(self, name, config={}):
        super().__init__(name, config)
        ## IP address of the cockpit computer.
        if not(hasattr(self, 'ipAddress')):
            self.ipAddress = "127.0.0.1"
        ## Name used to represent us to the outside world.
        self.name = 'mui'
        ## Auto-incrementing port ID.
        self.uniquePortID = 7700
        ## Maps registered functions to the ServerDaemon instances
        # used to serve them.
        self.funcToDaemon = {}


    def getHandlers(self):
        return [cockpit.handlers.server.ServerHandler("Cockpit server", "server",
                {'register': self.register,
                 'unregister': self.unregister})]
                

    ## Register a new function. Create a daemon to listen to calls
    # on the appropriate port; those calls will be forwarded to
    # the registered function. Return a URI used to connect to that
    # daemon from outside.
    def register(self, func, localIP = None):
        self.uniquePortID += 1
        ipAddress = self.ipAddress
        if localIP is not None:
            # Use the alternate address instead.
            ipAddress = localIP
        daemon = ServerDaemon(self.name, func, self.uniquePortID, ipAddress)
        self.funcToDaemon[func] = daemon
        daemon.serve()
        return 'PYRO:%s@%s:%d' % (self.name, ipAddress, self.uniquePortID)


    ## Stop a daemon.
    def unregister(self, func):
        if func in self.funcToDaemon:
            self.funcToDaemon[func].stop()
            del self.funcToDaemon[func]



class ServerDaemon:
    def __init__(self, name, func, port, host):
        self.name = name
        self.func = func
        self.daemon = Pyro4.Daemon(port = port, host = host)
        self.daemon.register(self, name)


    ## Handle function calls by forwarding them to self.func.
    @cockpit.util.threads.callInNewThread
    def serve(self):
        self.daemon.requestLoop()


    ## Stop the daemon.
    def stop(self):
        # Per the documentation, these functions must be called
        # in separate threads, or else the process will hang.
        threading.Thread(target=self.daemon.close, name="server-close").start()
        threading.Thread(target=self.daemon.shutdown, name="server-shutdown").start()


    ## Receive a function call from outside.
    # Note that if our caller throws an exception, then we do not propagate
    # it to the client; the assumption is that it's our fault and there's
    # nothing the client can do about the failure.
    def receiveData(self, *args):
        try:
            self.func(*args)
        except Exception as e:
            cockpit.util.logger.log.error("ServerDaemon [%s] failed its callback: %s" % (self.name, e))
            cockpit.util.logger.log.error(traceback.format_exc())
