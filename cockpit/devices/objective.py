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

import re
import typing

import cockpit.devices.device
from cockpit.handlers.objective import ObjectiveHandler


def _parse_three_number_tuple(string: str) -> typing.Tuple[str, str, str]:
    # Note the capture of '.*?' which is non-greddy to avoid capturing
    # an optional comma/spaces at the end in cases like '(1,1,1 , )'.
    match = re.search(r"^\s*\(\s*(.*?)\s*,?\s*\)\s*$", string)
    if not match:
        raise Exception("failed to match a tuple in '%s'" % string)
    values = match[1].split(",")
    if len(values) != 3:
        raise Exception(
            "failed to find 3 elements inside match '%s'" % match[1]
        )
    return tuple([x.strip() for x in values])


class ObjectiveDevice(cockpit.devices.device.Device):
    """Objective device.

    While this device wraps an objective, it actually wraps the whole
    light path originating from that objective, which is why it
    includes the attributes `pixel_size`, `transform`, and `offset`.

    The configuration section for an `ObjectiveDevice` takes the
    following keys:

    ``pixel_size`` (required)
      Amount of sample viewed by the pixel, not the physical size of the
      pixel sensor, in microns.

    ``transform`` (optional)
      Defaults to `(0, 0, 0)`.

    ``offset`` (optional)
      Defaults to `(0, 0, 0)`.

    ``colour``
      Defaults to `(1.0, 1.0, 1.0)` (white).

    ``lensID`` (optional)
      Lens identification number, to be recorded on the saved dv/mrc
      files.  Defaults to `0`.

    For example::

    .. code:: ini

        [60x water]
        type: cockpit.devices.objective.ObjectiveDevice
        pixel_size: 0.1
        transform: (1, 0, 0)
        offset: (-100, 50, 0)
        colour: (1.0, .5, .5)
        lensID: 10611

    """

    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        super().__init__(name, config)
        self._pixel_size = float(config["pixel_size"])
        self._transform = (0, 0, 0)
        self._offset = (0, 0, 0)
        self._colour = (1.0, 1.0, 1.0)
        self._lens_ID = 0

        if "lensid" in config:
            self._lens_ID = int(config["lensid"])

        if "transform" in config:
            values = _parse_three_number_tuple(config["transform"])
            self._transform = tuple([int(x) for x in values])
            if any([x not in [0, 1] for x in self._transform]):
                raise ValueError(
                    "invalid transform config '%s'" % config["transform"]
                )

        if "offset" in config:
            values = _parse_three_number_tuple(config["offset"])
            self._offset = tuple([int(x) for x in values])

        if "colour" in config:
            values = _parse_three_number_tuple(config["colour"])
            self._colour = tuple([float(x) for x in values])
            if not all([0.0 <= x <= 1.0 for x in self._colour]):
                raise ValueError(
                    "invalid colour config '%s'" % config["colour"]
                )

    def getHandlers(self) -> typing.List[ObjectiveHandler]:
        handler = ObjectiveHandler(
            name=self.name,
            group_name="miscellaneous",
            pixel_size=self._pixel_size,
            transform=self._transform,
            offset=self._offset,
            colour=self._colour,
            lens_ID=self._lens_ID,
        )
        return [handler]
