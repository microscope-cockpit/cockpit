#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2024 David Miguel Susano Pinto
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

import cockpit


class TestGetHelp(unittest.TestCase):
    """Test getting help text / usage from command line options.

    This test was added to ensure that the SystemExit exception
    triggered by argparse when handling `--help` is not accidentally
    caught to be displayed in a GUI like a "real" exception.

    """
    def test(self):
        with self.assertRaises(SystemExit) as cm:
            cockpit.main(["cockpit", "--help"])
        self.assertEqual(
            cm.exception.code, 0, "exit code from --help should be zero"
        )


if __name__ == '__main__':
    unittest.main()
