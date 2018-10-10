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


import threading
from itertools import chain
import re

## This module handles the event-passing system between the UI and the 
# devices. Objects may publish events, subscribe to them, and unsubscribe from
# them.

## Define common event strings here. This way, they're here for reference,
# and can be used elsewhere to avoid errors due to typos.
EXPERIMENT_EXECUTION = 'experiment execution'
EXPERIMENT_COMPLETE = 'experiment complete'
UPDATE_STATUS_LIGHT = 'update status light'
PREPARE_FOR_EXPERIMENT = 'prepare for experiment'
CLEANUP_AFTER_EXPERIMENT = 'cleanup after experiment'
LIGHT_SOURCE_ENABLE = 'light source enable'
STAGE_POSITION = 'stage position'
STAGE_MOVER = 'stage mover'
STAGE_STOPPED = 'stage stopped'
USER_ABORT = 'user abort'
MOSAIC_UPDATE = 'mosaic update'
NEW_IMAGE = 'new image %s' # must be suffixed with image source
SETTINGS_CHANGED = 'settings changed %s' # must be suffixed with device/handler name
EXECUTOR_DONE = 'executor done %s' # must be sufficed with device/handler name
## TODO - make changes throughout to use the string variables defined above.

## Maps event types to lists of (priority, function) tuples to call when
# those events occur.
eventToSubscriberMap = {}

## As eventToSubscriberMap, except that these subscribers only care about the
# next event (i.e. they unsubscribe as soon as the event happens once).
eventToOneShotSubscribers = {}

## Lock around the above two dicts.
subscriberLock = threading.Lock()

## Pass the given event to all subscribers.
def publish(eventType, *args, **kwargs):
    for priority, subscribeFunc in eventToSubscriberMap.get(eventType, []):
        try:
            subscribeFunc(*args, **kwargs)
        except:
            print('Error in subscribed func %s in %s.' % (subscribeFunc.__name__,
                                                         subscribeFunc.__module__))

    while True:
        try:
            with subscriberLock:
                subscribeFunc = eventToOneShotSubscribers[eventType].pop()
        except:
            # eventType not in eventToOneShotSubscibers or list is empty.
            break
        try:
            subscribeFunc(*args, **kwargs)
        except:
            print('Error in subscribed func %s in %s' % (subscribeFunc.__name__,
                                                         subscribeFunc.__module__))



## Add a new function to the list of those to call when the event occurs.
# \param priority Determines what order functions are called in when the event
#        occurs. Lower numbers go sooner.
def subscribe(eventType, func, priority = 100):
    with subscriberLock:
        if eventType not in eventToSubscriberMap:
            eventToSubscriberMap[eventType] = []
        eventToSubscriberMap[eventType].append((priority, func))
        eventToSubscriberMap[eventType].sort(key=lambda x: x[0])


## Add a new function to do a one-shot subscription.
def oneShotSubscribe(eventType, func):
    with subscriberLock:
        if eventType not in eventToOneShotSubscribers:
            eventToOneShotSubscribers[eventType] = []
        eventToOneShotSubscribers[eventType].append(func)


## Remove a function from the list of subscribers.
def unsubscribe(eventType, func):
    with subscriberLock:
        curSubscribers = eventToSubscriberMap.get(eventType, [])
        for i, (priority, subscriberFunc) in enumerate(curSubscribers):
            if func == subscriberFunc:
                del curSubscribers[i]
                return


## Clear one-shot subscribers on abort. Usually, these were subscribed
# by executeAndWaitFor, which leaves the calling thread waiting for a
# lock to be released. On an abort, that event may never happen.
def clearOneShotSubscribers(pattern=None):
    global eventToOneShotSubscribers
    if pattern is None:
        with subscriberLock:
            for subscriber in chain(*eventToOneShotSubscribers.values()):
                if hasattr(subscriber, '__abort__'):
                    subscriber.__abort__()
            eventToOneShotSubscribers = {}
    else:
        with subscriberLock:
            # Need to make list from filter to avoid dict length change errors
            # in python 3.
            clearEvents = list(filter(lambda x: re.match(pattern, x), eventToOneShotSubscribers))
            for evt in clearEvents:
                for subscriber in eventToOneShotSubscribers[evt]:
                    if hasattr(subscriber, '__abort__'):
                        subscriber.__abort__()
                    eventToOneShotSubscribers[evt].remove(subscriber)
                if not eventToOneShotSubscribers[evt]:
                    # list is empty
                    del(eventToOneShotSubscribers[evt])

subscribe('user abort', clearOneShotSubscribers)


## Call the specified function with the provided arguments, and then wait for
# the named event to occur.
def executeAndWaitFor(eventType, func, *args, **kwargs):
    newLock = threading.Lock()
    newLock.acquire()
    result = []
    def releaser(*args):
        result.extend(args)
        newLock.release()
    # Add a method to release the lock in the event of an abort event.
    releaser.__abort__ = lambda: newLock.release()
    oneShotSubscribe(eventType, releaser)
    func(*args, **kwargs)
    # Note that since newLock is already locked, this will block until it is
    # released.
    with newLock:
        if len(result) == 1:
            return result[0]
        return result


## Call the specified function with the provided arguments, and then wait for
# either the named event to occur or the timeout to expire.
def executeAndWaitForOrTimeout(eventType, func, timeout, *args, **kwargs):
    # Timeout implemented with a condition.
    newCondition = threading.Condition(threading.Lock())
    # Mutable flag to show whether or not releaser called.
    released = [False]
    # Mutable object to store results.
    result = []

    def releaser(*args):
        # Append arguments to result.
        result.extend(args)
        # Show that releaser called.
        released[0] = True
        # Notify condition.
        with newCondition:
            newCondition.notify()

    oneShotSubscribe(eventType, releaser)
    func(*args, **kwargs)

    # If event has not already happened, wait for notification or timeout.
    if not released[0]:
        with newCondition:
            # Blocks until another thread calls notify, or timeout.
            newCondition.wait(timeout)

    if released[0]:
        if len(result) == 1:
            return result[0]
        return result
    else:
        ## Timeout expired
        # Unsubscribe to keep subscription tables tidy.
        with subscriberLock:
            curSubscribers = eventToOneShotSubscribers.get(eventType, [])
            for i, subscriberFunc in enumerate(curSubscribers):
                if func == subscriberFunc:
                    del curSubscribers[i]
        # Raise an exception to indicate timeout.
        raise Exception('Event timeout: %s, %s' % (eventType, func))
