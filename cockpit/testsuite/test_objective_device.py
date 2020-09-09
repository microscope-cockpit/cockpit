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

import unittest
import typing

import cockpit.devices.objective


class TestParseTupleOfNumbers(unittest.TestCase):
    def assertParsing(
        self, to_parse: str, expected: typing.Tuple[str, str, str]
    ) -> None:
        self.assertTupleEqual(
            cockpit.devices.objective._parse_three_number_tuple(to_parse),
            expected,
        )

    def test_parse_compact(self):
        self.assertParsing("(1,2,3)", ("1", "2", "3"))

    def test_parse_whitespace(self):
        self.assertParsing(" ( 1 , 2 , 3 ) ", ("1", "2", "3"))

    def test_parse_trailing_comma(self):
        self.assertParsing(" ( 1 , 2 , 3 , ) ", ("1", "2", "3"))
        self.assertParsing(" ( 1 , 2 , 3, ) ", ("1", "2", "3"))
        self.assertParsing(" ( 1 , 2 , 3 ,) ", ("1", "2", "3"))


class TestObjective(unittest.TestCase):
    def test_construct(self):
        config = {
            "pixel_size": "0.1",
            "transform": "(1, 0, 0)",
            "offset": "(-100, 50, 0)",
            "colour": "(1.0, .5, .5)",
            "lensid": "10611",
        }
        obj = cockpit.devices.objective.ObjectiveDevice("60x water", config)
        handlers = obj.getHandlers()
        self.assertEqual(len(handlers), 1)
        for attr, expected in [
            ("pixel_size", 0.1),
            ("transform", (1, 0, 0)),
            ("offset", (-100, 50, 0)),
            ("colour", (1.0, 0.5, 0.5)),
            ("lens_ID", 10611),
        ]:
            self.assertEqual(getattr(handlers[0], attr), expected)

    def test_colour_range_validation(self):
        """ObjectiveDevice checks colour is in the [0 1] range"""
        with self.assertRaisesRegex(ValueError, "invalid colour config"):
            cockpit.devices.objective.ObjectiveDevice(
                "60x Water", {"pixel_size": ".1", "colour": "(255, 0, 0)"}
            )


if __name__ == "__main__":
    unittest.main()
