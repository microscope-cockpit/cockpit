#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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

"""Cockpit events module is a topic based publish-subscriber system.

This module is meant as a event passing middleware between the UI,
using :class:`wx.Event`, and the individual devices and handlers which
are independent on wxPython.

In addition to the :class:`Publisher` class, there is a singleton
``Publisher`` instance used throughout the Cockpit program.  The
module functions :func:`publish`, :func:`subscribe`, and
:func:`unsubscribe` are pass-through functions to this singleton.

The global singleton means that any code may subscribe to an event,
such as ``STAGE_POSITION`` or ``CAMERA_ENABLE``.  Likewise any code
may publish an event, along with associated data.  When an event is
published, all subscribers to the event have their functions called.
For example::

    from cockpit import events

    # subscribe obj.on_user_abort so that it is called when the
    # USER_ABORT event is published.
    events.subscribe(events.USER_ABORT,
                     obj.on_user_abort)

    # Publish the CAMERA_ENABLE event as well as the associated data,
    # camera handler and whether it has been enabled or disabled.
    events.publish(events.CAMERA_ENABLE,
                   camera_handler, is_enabled)

Beware
======

While the global singleton can make it easy to solve some problems, it
can be easily abused and leads to situations where it's not clear what
happens when an event is published.

GUI code should not subscribe to events directly and instead should
use :class:`cockpit.gui.EvtEmitter`.  Events between GUI components
should not require this events systems and should instead be using
wx's own event loop.

Available events
================

Anything can be "published".  The following is a list of events that
the system expects.

``CAMERA_ENABLE``

``CLEANUP_AFTER_EXPERIMENT``

``DEVICE_STATUS``

``EXECUTOR_DONE % executor_name``

``EXPERIMENT_COMPLETE``
  The entirety of an experiment has finished execution.

``EXPERIMENT_EXECUTION``
  Some component of the currently-running experiment has finished.

``LIGHT_SOURCE_ENABLE``
  The light source associated with the provided handler has been
  enabled / disabled for taking images.

``MOSAIC_UPDATE``

``NEW_IMAGE % camera name``
  An image has arrived for the camera with the given name.

``PREPARE_FOR_EXPERIMENT``
  An experiment is about to be executed, so devices should prepare
  themselves.

``SETTINGS_CHANGED % deviceor_handler_name``

``STAGE_MOVER``
  A ``StagePositioner`` handler is moving.

``STAGE_POSITION``
  The stage currently is at the specified position.

``STAGE_STOPPED``
  A ``StagePositioner`` handler has stopped moving.

``STAGE_TOP_BOTTOM``

``UPDATE_STATUS_LIGHT``

``USER_ABORT``
  The user clicked on the Abort button.

``VIDEO_MODE_TOGGLE``

``"filter change"``

``"image pixel info"``
  The mouse has moved over a camera view, and the specified
  coordinates have the given value.

``"new site"``
  The user has marked a position as being of interest.

``"objective change"``
  The objective has been changed.

``"site deleted"``
  The specified Site is to be forgotten.

``"soft safety limit"``
  The software-enforced motion limits for the given axis (summing all
  stage-positioner devices) have been changed.

``"stage step index"``
  Which Handler is currently being used to move the stage has been
  changed; the Handlers are arranged in order of maximum range of
  motion.

``"stage step size"``
  The amount of distance the stage will move when the user uses the
  numeric keypad has changed.

"""

import collections
import sys
import threading
import traceback
import typing

## Define common event strings here. This way, they're here for reference,
# and can be used elsewhere to avoid errors due to typos.
DEVICE_STATUS = 'device status'
EXPERIMENT_EXECUTION = 'experiment execution'
EXPERIMENT_COMPLETE = 'experiment complete'
UPDATE_STATUS_LIGHT = 'update status light'
PREPARE_FOR_EXPERIMENT = 'prepare for experiment'
CLEANUP_AFTER_EXPERIMENT = 'cleanup after experiment'
LIGHT_SOURCE_ENABLE = 'light source enable'
CAMERA_ENABLE = 'camera enable'
STAGE_POSITION = 'stage position'
STAGE_MOVER = 'stage mover'
STAGE_STOPPED = 'stage stopped'
STAGE_TOP_BOTTOM = 'stage saved top/bottom'
USER_ABORT = 'user abort'
MOSAIC_UPDATE = 'mosaic update'
NEW_IMAGE = 'new image %s' # must be suffixed with image source
SETTINGS_CHANGED = 'settings changed %s' # must be suffixed with device/handler name
EXECUTOR_DONE = 'executor done %s' # must be sufficed with device/handler name
VIDEO_MODE_TOGGLE = 'video mode toggle'


_Subscriber = typing.Callable[..., None]


class Publisher:
    def __init__(self) -> None:
        # type: typing.Dict[str, typing.List[_Subscriber]]
        self._subscriptions = collections.defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, func: _Subscriber) -> None:
        """Subscribe callable to specified event.

        Args:
            event: event type/name (global constants in this module.)
            func: function to be called when the named event happens.
        """
        with self._lock:
            self._subscriptions[event].append(func)

    def unsubscribe(self, event: str, func: _Subscriber) -> None:
        """Unsubscribe callable to specified event."""
        with self._lock:
            try:
                self._subscriptions[event].remove(func)
            except ValueError:
                pass # ignore func not in list error

    def publish(self, event: str, *args, **kwargs):
        """Call all functions subscribed to specific event with given arguments.
        """
        for func in self._subscriptions[event]:
            try:
                func(*args, **kwargs)
            except:
                sys.stderr.write('Error in subscribed callable %s.%s().  %s'
                                 % (func.__module__, func.__name__,
                                    traceback.format_exc()))


class OneShotPublisher(Publisher):
    """Publisher that automatically unsubscribes after a publication.

    Like `Publisher`, except that the subscribers only care about the
    next event (i.e. they unsubscribe as soon as the event happens
    once).

    """
    def publish(self, event: str, *args, **kwargs) -> None:
        try:
            super().publish(event, *args, **kwargs)
        finally:
            # _subscriptions is a defaultdict but pop will still raise
            # if key is missing, so we need None as pop's default.
            self._subscriptions.pop(event, None)

    def clear(self) -> None:
        with self._lock:
            for subscriptions in self._subscriptions.values():
                for subscription in subscriptions:
                    if hasattr(subscription, '__abort__'):
                        subscription.__abort__()
            self._subscriptions.clear()


# Global singletons
_publisher = Publisher()
_one_shot_publisher = OneShotPublisher()

def subscribe(event: str, func: _Subscriber) -> None:
    return _publisher.subscribe(event, func)

def unsubscribe(event: str, func: _Subscriber) -> None:
    return _publisher.unsubscribe(event, func)

def publish(event: str, *args, **kwargs) -> None:
    _publisher.publish(event, *args, **kwargs)
    _one_shot_publisher.publish(event, *args, **kwargs)

def oneShotSubscribe(event: str, func: _Subscriber):
    return _one_shot_publisher.subscribe(event, func)


# Clear one-shot subscribers on abort.  Usually, these were subscribed
# by executeAndWaitFor, which leaves the calling thread waiting for a
# lock to be released.  On an abort, that event may never happen.
_publisher.subscribe(USER_ABORT, _one_shot_publisher.clear)


## Call the specified function with the provided arguments, and then wait for
# the named event to occur.
def executeAndWaitFor(eventType: str, func: _Subscriber, *args, **kwargs):
    return executeAndWaitForOrTimeout(eventType, func, None, *args, **kwargs)


## Call the specified function with the provided arguments, and then wait for
# either the named event to occur or the timeout to expire.
def executeAndWaitForOrTimeout(eventType: str, func: _Subscriber,
                               timeout: typing.Optional[float],
                               *args, **kwargs):
    global _one_shot_publisher

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
    def aborter():
        released[0] = True
        with newCondition:
            newCondition.notify()
    # Add a method to notify condition in the event of an abort event.
    releaser.__abort__ = aborter

    _one_shot_publisher.subscribe(eventType, releaser)
    try:
        func(*args, **kwargs)
    except:
        _one_shot_publisher.unsubscribe(eventType, releaser)
        raise

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
        _one_shot_publisher.unsubscribe(eventType, releaser)
