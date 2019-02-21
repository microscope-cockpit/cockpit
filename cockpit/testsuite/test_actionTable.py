#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
## Copyright (C) 2019 Thomas Park <thomasparks@outlook.com>
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

import decimal
import unittest

import cockpit.depot
import cockpit.experiment.actionTable
import cockpit.handlers.deviceHandler


class _MockDeviceHandler(cockpit.handlers.deviceHandler.DeviceHandler):
    def __init__(self, name='mock', groupName='testsuite'):
        super().__init__(name, groupName, isEligibleForExperiments=False,
                         callbacks={}, deviceType=cockpit.depot.GENERIC_DEVICE)


class TestActionTable(unittest.TestCase):
    def setUp(self):
        self.action_table = cockpit.experiment.actionTable.ActionTable()

    def test___getitem___single(self):
        self.action_table.addAction(0, None, None)
        self.assertEqual((0, None, None), self.action_table.__getitem__(0))

    def test___getitem___handler_is_unmodified(self):
        handler = _MockDeviceHandler()
        self.action_table.addAction(0, handler, None)
        self.assertTrue(self.action_table.__getitem__(0)[1] is handler)

    def test___getitem___last(self):
        for n in range(5):
            self.action_table.addAction(n, None, None)
        self.assertEqual((4, None, None), self.action_table.__getitem__(-1))

    def test___init___length(self):
        self.assertEqual(len(self.action_table), 0)

    def test___init___times(self):
        self.assertEqual(self.action_table.getFirstAndLastActionTimes(),
                         (None, None))

    def test___len___emtpy(self):
        self.assertEqual(0, self.action_table.__len__())

    def test__len___nonemtpy(self):
        for n in range(5):
            self.action_table.addAction(n, None, None)
        self.assertEqual(5, self.action_table.__len__())

    def test_lenFunc(self):
        for n in range(5):
            self.action_table.addAction(n, None, None)
        self.assertEqual(len(self.action_table), self.action_table.__len__())

    def test___repr__(self):
        """All this does currently is call prettyString.
        """
        self.assertTrue(isinstance(self.action_table.__repr__(), str))

    ## prettystring needs to handle diffrent handlers
    #                               None-events
    #                               no events at all

    def test_pretty_string_emtpy(self):
        self.assertEqual(self.action_table.prettyString(), '')

    def test_pretty_string_non_emtpy_length(self):
        handler = _MockDeviceHandler()
        n_actions = 5
        for i in range(n_actions):
             self.action_table.addAction(i, handler, None)
        self.assertEqual(len(self.action_table.prettyString().splitlines()),
                         n_actions)

    def test_pretty_string_format(self):
        """The format returned is the repr's of 'time handler.name parameter'
        as a string.
        """
        handler = _MockDeviceHandler()
        self.action_table.addAction(1, handler, None)
        s = self.action_table.prettyString()
        time, name, parameter = s.split()

        try:
            float(time)
        except ValueError:
            self.assertTrue(False)
        self.assertEqual(name, handler.name)
        self.assertEqual(parameter, 'None')

    def test___setitem__(self):
        pass
        # self.assertEqual(expected, action_table.__setitem__(index, val))
        # assert False # TODO: implement your test here

    def test_addAction(self):
        self.action_table.addAction(0, None, None)
        self.assertEqual(1, len(self.action_table))

    def test_addAction_sets_time(self):
        self.action_table.addAction(1, None, None)
        self.action_table.addAction(3, None, None)
        self.assertEqual((1, 3), self.action_table.getFirstAndLastActionTimes())

    def test_addToggle(self):
        # Toggles are represented by 2 events
        self.action_table.addToggle(1, _MockDeviceHandler())
        self.assertEqual(2, len(self.action_table))

    def test_addToggle_time_delta(self):
        # Toggles should be seperated by a single dt
        self.action_table.addToggle(1, _MockDeviceHandler())
        dt = self.action_table.toggleTime
        self.assertEqual(self.action_table[0][0] + dt, self.action_table[1][0])

    def test_clearBadEntries(self):
        # If a user sets a position in the table to None, it should be removed.
        self.action_table.addAction(1, None, None)
        self.assertEqual(1, len(self.action_table))
        self.action_table[0] = None
        self.assertEqual(1, len(self.action_table))
        self.action_table.clearBadEntries()
        self.assertEqual(0, len(self.action_table))

    def test_clearBadEntries_no_bad_entries(self):
        # Nothing should happen to normal entries
        self.action_table.addAction(1, None, None)
        self.assertEqual(1, len(self.action_table))
        self.action_table.clearBadEntries()
        self.assertEqual(1, len(self.action_table))

    def test_enforcePositiveTimepoints(self):
        self.action_table.addAction(-1, None, None)
        # 1 element so sorted
        self.action_table.enforcePositiveTimepoints()
        self.assertEqual(0, self.action_table[0][0])

    def test_enforcePositiveTimepoints_multiple_maintain_gap(self):
        self.action_table.addAction(-1, None, None)
        self.action_table.addAction(0, None, None)
        # 2 elements in sorted order
        self.action_table.enforcePositiveTimepoints()
        self.assertEqual(0, self.action_table[0][0])
        self.assertEqual(1, self.action_table[1][0])

    @unittest.expectedFailure
    def test_enforcePositiveTimepoints_unsorted(self):
        """Enforcing the sorted order should move all elements forward by
        the most negative elements time.
        """
        timepoints = [0, -1]
        for time in timepoints:
            self.action_table.addAction(time, None, None)

        self.action_table.enforcePositiveTimepoints()

        proper_times = set([t-min(timepoints) for t in timepoints])
        corrected_times = set([action[0] for action in self.action_table])
        self.assertEqual(proper_times, corrected_times)

    def test_getFirstAndLastActionTimes_emtpy(self):
        ## XXX: Is this the correct response?
        self.assertEqual(self.action_table.getFirstAndLastActionTimes(),
                         (None, None))

    def test_getFirstAndLastActionTimes(self):
        for t in range(5):
            self.action_table.addAction(t, None, None)

        self.assertEqual((0, 4), self.action_table.getFirstAndLastActionTimes())

    def test_getFirstAndLastActionTimes_close_decimal(self):
        """Actions may be very close, so even at high precision the times
        should differ.
        """
        self.action_table.addAction(decimal.Decimal(0), None, None)
        self.action_table.addAction(decimal.Decimal(1e-30), None, None)
        times = self.action_table.getFirstAndLastActionTimes()
        self.assertNotEqual(*times)

    def test_getLastActionFor(self):
        handler = _MockDeviceHandler()
        self.action_table.addAction(0, handler, None)
        self.assertEqual(self.action_table.getLastActionFor(handler),
                         (0, None))

    # TODO: test marktime, no elements, no elements that need to be moved
    def test_shiftActionsBack(self):
        """Tests that moving actions back introduces moves them later in time.
        """
        self.action_table.addAction(1, None, None)
        self.action_table.shiftActionsBack(0, 1)
        self.assertEqual(2, self.action_table[0][0])

    def test_sort_emtpy(self):
        self.action_table.sort()

    def test_sort_sorted(self):
        for t in range(5):
            self.action_table.addAction(t, None, None)
        self.action_table.sort()
        for i, action in enumerate(self.action_table):
            self.assertLessEqual(self.action_table[i][0], action[0])

    def test_sort_reversed(self):
        for t in range(4, -1, -1):
            self.action_table.addAction(t, None, None)
        self.action_table.sort()
        for i, action in enumerate(self.action_table):
            self.assertLessEqual(self.action_table[i][0], action[0])

    def test_creation(self):
        pass

    def test_add_action_returns_time(self):
        self.assertEqual(0.1, self.action_table.addAction(0.1, None, None))


if __name__ == '__main__':
    unittest.main()
