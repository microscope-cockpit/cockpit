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

"""The "Model" behind Cockpit UI components.

Historically, this subpackage was limited to provide interfaces to the
GUI for when multiple handlers needed to be aggregated together to
perform complex tasks.  As data and logic were extracted from the GUI
components, it as been moved here.

"""


import re
import typing

import wx

import cockpit.events
from cockpit.handlers.objective import ObjectiveHandler


EVT_OBJECTIVE_CHANGED = wx.PyEventBinder(wx.NewEventType())


class Objectives(wx.EvtHandler):
    """Container for the available objectives.

    At any time, only one objective is selected, which prevents its use
    on a system where different cameras image through different
    objectives at the same time (see `cockpit issue #554
    <https://github.com/MicronOxford/cockpit/issues/554>`_).

    Events emitted by this class
    ----------------------------

    Handlers bound for the following event types will receive a
    ``wx.CommandEvent`` parameter:

    - ``EVT_OBJECTIVE_CHANGED`` when the objective has been changed.
      The `String` attribute of the event instance is set to the new
      objective name.

    """

    def __init__(self, handlers: typing.Sequence[ObjectiveHandler]) -> None:
        super().__init__()
        if not handlers:
            raise ValueError("list of objective handlers must not be empty")
        self._handlers = list(handlers)
        self._current = self._handlers[0]

    def GetHandlers(self) -> typing.List[ObjectiveHandler]:
        """:class:`ObjectiveHandler` for all objectives."""
        return self._handlers.copy()

    def GetCurrent(self) -> ObjectiveHandler:
        """:class:`ObjectiveHandler` for current objective."""
        return self._current

    def GetNames(self) -> typing.List[str]:
        """Names for all objectives."""
        return [h.name for h in self._handlers]

    def GetNamesSorted(self) -> typing.List[str]:
        """List of all objective names sorted by magnification."""
        # FIXME: we should not do this.  Instead, objective device and
        # handlers should have a magnification field (see issue #139).
        def parse_magnification(name):
            match = re.search(r"^([0-9.])+x", name)
            if match is None:
                raise Exception("failed to parse magnification from %s" % name)
            return float(match[1])

        return sorted(self.GetNames(), key=parse_magnification)

    def ChangeObjective(self, name: str) -> None:
        try:
            self._current = next(
                filter(lambda h: h.name == name, self._handlers)
            )
        except StopIteration:
            raise ValueError("no objective handler for name '%s'" % name)
        event = wx.CommandEvent(EVT_OBJECTIVE_CHANGED.typeId)
        event.SetString(name)
        self.QueueEvent(event)
        # Camera devices care when objectives changes to update their
        # transforms so we need to publish a cockpit event as well.
        cockpit.events.publish("objective change", self._current)

    def GetName(self) -> str:
        """Convenience getter for name of current objective."""
        return self._current.name

    def GetPixelSize(self) -> float:
        """Convenience getter for pixel size of current objective."""
        return self._current.pixel_size

    def GetOffset(self) -> typing.Tuple[int, int, int]:
        """Convenience getter for offset of current objective."""
        return self._current.offset

    def GetColour(self) -> typing.Tuple[float, float, float]:
        """Convenience getter for colour of current objective."""
        return self._current.colour
