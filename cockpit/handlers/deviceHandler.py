#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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

import threading

from cockpit import events
import cockpit.util.threads


## A DeviceHandler acts as the interface between the GUI and the device module.
# In other words, it tells the GUI what the device does, and translates GUI
# events into commands for the device. A variety of stock DeviceHandler 
# subclasses are available for representing common types of hardware. In order
# to make your hardware accessible to the UI, you need to make a Device, and
# implement its getHandlers() method so that it returns a list of
# DeviceHandlers. 
#
# The device handler now supports multiple UI controls by allowing them
# to watch for device parameter changes: each control should use addWatch
# to register a callback that takes the new value as its only argument:
#    addWatch(parameterName, callback)

## Device states
class STATES():
    error = -1
    disabled = 0
    enabled = 1
    enabling = 2
    constant = 3
    busy = 4


class DeviceHandler:
    ## \param name The name of the device being controlled. This should be
    #         unique, as it is used to indicate the specific DeviceHandler
    #         in many callback functions. 
    # \param groupName The name of the group of objects this object falls
    #        under. Multiple DeviceHandlers can correspond to a single group
    #        when their purpose is similar.
    # \param callbacks Mapping of strings to functions. Each Handler has a 
    #        different selection of functions that must be filled in by the 
    #        Device that created it. Refer to the Handler's constructor.
    # \param deviceType Type of device this is; each subclass of DeviceHandler
    #        should have a distinct deviceType. Normal users don't need to 
    #        worry about this as it is provided automatically by the 
    #        DeviceHandler subclass. 
    # \param isEligibleForExperiments True if the device can be used in
    #        experiments (i.e. data collections).
    @staticmethod
    def cached(f):
        def wrapper(self, *args, **kwargs):
            key = (f, args, frozenset(sorted(kwargs.items())))
            # Previously, I checked for key existence and, if it wasn't
            # found, added the key and value to the cache, then returned
            # self.__cache[key]. If another thread calls reset_cache 
            # between the cache assignment and the return, this can
            # cause a KeyError, so instead I now put the result in a 
            # local variable, cache it, then return the local.
            try:
                return self.__cache[key]
            except KeyError:
                result = f(self, *args, **kwargs)
                self.__cache[key] = result
                return result
        return wrapper


    @staticmethod
    def reset_cache(f=None):
        def wrapper(self, *args, **kwargs):
            self.__cache = {}
            if f is None:
                return f
            else:
                return f(self, *args, **kwargs)
        return wrapper


    def __init__(self, name, groupName,
                 isEligibleForExperiments, callbacks, deviceType):
        # Set up dict for attribute-change listeners.
        super().__init__()
        self._watches = {}
        self.state = None
        self.__cache = {}
        self.name = name
        self.groupName = groupName
        self.callbacks = callbacks
        self.isEligibleForExperiments = isEligibleForExperiments
        self.deviceType = deviceType
        # A set of controls that listen for device events.
        self.enableLock = threading.Lock()
        self.clear_cache = self.__cache.clear


    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if not hasattr(self, '_watches'):
            return
        if key not in self._watches:
            return
        for cb in self._watches[key]:
            try:
                cb(value)
            except:
                # Should maybe clean up failing watch callbacks.
                pass



    # Define __lt__ to make handlers sortable.
    def __lt__(self, other):
        return self.name.lower() < other.name.lower()


    ## Return a string that identifies the device.
    def getIdentifier(self):
        return "%s:%s" % (self.deviceType, self.name)

    ## Construct any necessary UI widgets for this Device to perform its job.
    # Return a WX sizer holding the result, or None if nothing is to be 
    # inserted into the parent object. 
    # \param parent The WX object that will own the UI.
    def makeUI(self, parent):
        if 'makeUI' in self.callbacks:
            return self.callbacks['makeUI'](parent)
        else:
            return None


    ## Publish any necessary events to declare our initial configuration to 
    # anything that cares. At this point, all device handlers should be 
    # initialized.
    def makeInitialPublications(self):
        getIsEnabled = getattr(self, 'getIsEnabled', None) or self.callbacks.get('getIsEnabled', None)
        if getIsEnabled:
            events.publish(events.DEVICE_STATUS, self, getIsEnabled())


    ## Do any final initaliaziton actions, now that all devices are set up,
    # all subscriptions have been made, and all initial publications are done.
    def finalizeInitialization(self):
        pass


    ## Return True if we can be used during experiments.
    def getIsEligibleForExperiments(self):
        return self.isEligibleForExperiments


    ## Generate a string of information that we want to save into the 
    # experiment file's header. There's limited space (800 characters) so
    # only important information should be preserved. This callback is 
    # optional; by default nothing is generated.
    def getSavefileInfo(self):
        if 'getSavefileInfo' in self.callbacks:
            return self.callbacks['getSavefileInfo'](self.name)
        return ''


    ## Do any necessary cleanup when an experiment is finished.
    # \param isCleanupFinal This boolean indicates if we're about to leap into
    #        a followup experiment. In that situation, some cleanup steps may
    #        be unnecessary and should be omitted for performance reasons.
    def cleanupAfterExperiment(self, isCleanupFinal = True):
        pass


    ## Debugging: print some pertinent info.
    def __repr__(self):
        return "<%s named %s in group %s>" % (self.deviceType, self.name, self.groupName)


    ## Add a watch on a device parameter.
    def addWatch(self, name, callback):
        if name not in self._watches:
            self._watches[name] = set()
        self._watches[name].add(callback)


    ## A function that any control can call to toggle enabled/disabled state.
    @cockpit.util.threads.callInNewThread
    def toggleState(self, *args, **kwargs):
        if self.state == STATES.enabling:
            # Already processing a previous toggle request.
            return
        getIsEnabled = getattr(self, 'getIsEnabled', None) or self.callbacks.get('getIsEnabled', None)
        setEnabled = getattr(self, 'setEnabled', None) or self.callbacks.get('setEnabled', None)
        if not all([getIsEnabled, setEnabled]):
            raise Exception('toggleState dependencies not implemented for %s.' % self.name)

        # Do nothing if lock locked as en/disable already in progress.
        if not self.enableLock.acquire(False):
            return
        events.publish(events.DEVICE_STATUS, self, STATES.enabling)
        try:
            setEnabled(not(getIsEnabled()))
        except Exception as e:
            events.publish(events.DEVICE_STATUS, self, STATES.error)
            raise Exception('Problem encountered en/disabling %s:\n%s' % (self.name, e))
        finally:
            self.enableLock.release()
        events.publish(events.DEVICE_STATUS, self, getIsEnabled())

    ## Add a toggle event to the action table.
    # Return time of last action, and response time before ready after trigger.
    def addToggle(self, time, table):
        table.addAction(time, self, True)
        table.addAction(time + table.toggleTime, self, False)
        return time + table.toggleTime, 0
