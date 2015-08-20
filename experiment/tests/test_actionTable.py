import unittest
from mock import Mock
from experiment.actionTable import ActionTable
import decimal


class TestActionTable(unittest.TestCase):

    def setUp(self):
        '''The setUp method is called before all tests, and restores a
        consistant enviroment.
        '''
        self.action_table = ActionTable()
        self.handler = Mock()
        self.handler.name = 'Mock'


    def test___getitem___single(self):
        self.action_table.addAction(0, None, None)
        self.assertEqual((0, None, None), self.action_table.__getitem__(0))


    def test___getitem___handler_is_unmodified(self):
        self.action_table.addAction(0, self.handler, None)
        self.assertTrue(self.action_table.__getitem__(0)[1] is self.handler)


    def test___getitem___last(self):
        for n in range(5):
            self.action_table.addAction(n, None, None)
        self.assertEqual((4, None, None), self.action_table.__getitem__(-1))


    def test___init___length(self):
        self.assertEqual(len(self.action_table), 0)


    def test___init___times(self):
        self.assertEqual(self.action_table.getFirstAndLastActionTimes(), (None, None))


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
        '''All this does currently is call prettyString.'''
        self.assertTrue(isinstance(self.action_table.__repr__(), str))


    ## prettystring needs to handle diffrent handlers
    #                               None-events
    #                               no events at all

    def test_pretty_string_emtpy(self):
        self.assertEqual(self.action_table.prettyString(), '')


    def test_pretty_string_non_emtpy_length(self):
        for n in range(5):
             self.action_table.addAction(n, self.handler, None)
        self.assertEqual(len(self.action_table.prettyString().splitlines()), 5)


    def test_pretty_string_format(self):
        '''The format returned is the repr's of 'time handler.name parameter'
        as a string.
        '''
        self.action_table.addAction(1, self.handler, None)
        s = self.action_table.prettyString()
        time, handler, parameter = s.split()

        try:
            float(time)
        except ValueError:
            self.assertTrue(False)
        self.assertEqual(handler, 'Mock')
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
        self.action_table.addToggle(1, None)
        self.assertEqual(2, len(self.action_table))


    def test_addToggle_time_delta(self):
        # Toggles should be seperated by a single dt
        self.action_table.addToggle(1, None)
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
        '''Enforcing the sorted order should move all elements forward by
        the most negative elements time.
        '''
        timepoints = [0, -1]
        for time in timepoints:
            self.action_table.addAction(time, None, None)

        self.action_table.enforcePositiveTimepoints()

        proper_times = set([t-min(timepoints) for t in timepoints])
        corrected_times = set([action[0] for action in self.action_table])
        self.assertEqual(proper_times, corrected_times)


    def test_getFirstAndLastActionTimes_emtpy(self):
        # Is this the correct response?
        self.assertEqual((None, None), self.action_table.getFirstAndLastActionTimes())


    def test_getFirstAndLastActionTimes(self):
        for t in range(5):
            self.action_table.addAction(t, None, None)

        self.assertEqual((0, 4), self.action_table.getFirstAndLastActionTimes())


    def test_getFirstAndLastActionTimes_close_decimal(self):
        '''Actions may be very close, so even at high precision the times
        should differ.
        '''
        self.action_table.addAction(decimal.Decimal(0), None, None)
        self.action_table.addAction(decimal.Decimal(1e-30), None, None)
        times = self.action_table.getFirstAndLastActionTimes()
        self.assertNotEqual(*times)


    def test_getLastActionFor(self):
        self.action_table.addAction(0, self.handler, None)
        self.assertEqual((0, None),
                         self.action_table.getLastActionFor(self.handler))


    # TODO: test marktime, no elements, no elements that need to be moved
    def test_shiftActionsBack(self):
        '''Tests that moving actions back introduces moves them later in time.
        '''
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
        for t in range(5)[::-1]:
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
