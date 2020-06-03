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

import collections
import json
import typing

import wx

import cockpit.events


EVT_CHANNEL_ADDED = wx.PyEventBinder(wx.NewEventType())
EVT_CHANNEL_REMOVED = wx.PyEventBinder(wx.NewEventType())


Channel = typing.Dict[str, typing.Any]

class Channels(wx.EvtHandler):
    """Map names to channel configurations.

    A channel configuration sets objective, light sources, and
    cameras.  It is the configuration to replicate the image
    acquisition settings.

    `Channels` keep the order of channels that are added.  While
    technically not needed for a map/dict object, this is used to
    construct GUI elements where it is important to keep the order for
    usability.  It is simpler to do it here than to require each GUI
    element does it itself.  The end result is that the user is in
    control of the order the channels are listed.

    Events emitted by this class
    ----------------------------

    Handlers bound for the following event types will receive a
    ``wx.CommandEvent`` parameter with the ``String`` attribute set to
    the associated channel name:

    - ``EVT_CHANNEL_ADDED``
    - ``EVT_CHANNEL_REMOVED``

    """
    def __init__(self) -> None:
        super().__init__()
        self._map = collections.OrderedDict() # type: typing.OrderedDict[str, Channel]

    @property
    def Names(self) -> typing.List[str]:
        return list(self._map.keys())

    def Get(self, name: str) -> Channel:
        return self._map[name]

    def Add(self, name: str, channel: Channel) -> None:
        """Add new channel. Use `Change` to modify existing channel."""
        if name in self._map:
            raise ValueError('channel \'%s\' already exists' % name)
        self._map[name] = channel
        event = wx.CommandEvent(EVT_CHANNEL_ADDED.typeId)
        event.SetString(name)
        self.QueueEvent(event)

    def Change(self, name: str, channel: typing.Dict) -> None:
        self._map[name] = channel

    def Remove(self, name: str) -> None:
        self._map.pop(name)
        event = wx.CommandEvent(EVT_CHANNEL_REMOVED.typeId)
        event.SetString(name)
        self.QueueEvent(event)

    def Update(self, other: 'Channels') -> None:
        """Update this instances with the channels from other."""
        # We call Add/Change instead of OrderedDict.update because the
        # add/remove events are meant for one channel change.  We
        # could have other events but that would make updating the GUI
        # elements more complicated.
        for name, channel in other._map.items():
            if name in self._map:
                self.Change(name, channel)
            else:
                self.Add(name, channel)


def CurrentChannel() -> Channel:
    """Returns current channel configuration."""
    # FIXME: we should be doing this directly, probably via a
    # DeviceDepot instance, and not use events.
    new_channel = {}
    cockpit.events.publish('save exposure settings', new_channel)
    return new_channel

def ApplyChannel(channel: Channel) -> None:
    """Apply the given channel configuration."""
    # FIXME: we should be doing this directly, probably via a
    # DeviceDepot instance, and not use events.
    cockpit.events.publish('load exposure settings', channel)


def SaveToFile(filepath: str, channels: Channels) -> None:
    with open(filepath, 'w') as fh:
        # We should not be accessing internal attributes but
        # alternatives seems overkill since Channels is so simple.
        json.dump(channels._map, fh, indent=2)

def LoadFromFile(filepath: str) -> Channels:
    with open(filepath, 'r') as fh:
        # We should not be doing this manually but alternatives seem
        # overkill since Channels is so simple.
        internal_map = json.load(fh)
    channels = Channels()
    for name, channel in internal_map.items():
        print('loading from file ', name)
        channels.Add(name, channel)
    return channels
