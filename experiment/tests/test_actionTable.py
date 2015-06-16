import unittest
from mock import Mock
from experiment.actionTable import ActionTable


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
            action_table.addAction(n, None, None)
        self.assertEqual((4, None, None), self.action_table.__getitem__(-1))

    def test___init___length(self):
        self.assertEqual(self.action_table.len(), 0)

    def test___init___times(self):
        self.assertEqual(self.action_table.getFirstAndLastActionTimes(), (None, None))

    def test___len___emtpy(self):
        self.assertEqual(0, self.action_table.__len__())

    def test__len___nonemtpy(self):
        for n in range(5):
            action_table.addAction(n, None, None)
        self.assertEqual(5, self.action_table.__len__())

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
        self.assertTrue(int(time) is int) # check that the time is a number
        self.assertEqual(handler, 'Mock')
        self.assertEqual(parameter, 'None')

    def test_pretty_string_del_event(self):
        pass

    def test___setitem__(self):
        pass
        # self.assertEqual(expected, action_table.__setitem__(index, val))
        # assert False # TODO: implement your test here

    def test_addAction(self):
        #
        # self.assertEqual(expected, action_table.addAction(time, handler, parameter))
        assert False # TODO: implement your test here

    def test_addToggle(self):
        #
        # self.assertEqual(expected, action_table.addToggle(time, handler))
        assert False # TODO: implement your test here

    def test_clearBadEntries(self):
        #
        # self.assertEqual(expected, action_table.clearBadEntries())
        assert False # TODO: implement your test here

    def test_enforcePositiveTimepoints(self):
        #
        # self.assertEqual(expected, action_table.enforcePositiveTimepoints())
        assert False # TODO: implement your test here

    def test_getFirstAndLastActionTimes(self):
        #
        # self.assertEqual(expected, action_table.getFirstAndLastActionTimes(canUseCache))
        assert False # TODO: implement your test here

    def test_getLastActionFor(self):
        #
        # self.assertEqual(expected, action_table.getLastActionFor(handler))
        assert False # TODO: implement your test here


    def test_shiftActionsBack(self):
        #
        # self.assertEqual(expected, action_table.shiftActionsBack(markTime, delta))
        assert False # TODO: implement your test here

    def test_sort(self):
        #
        # self.assertEqual(expected, action_table.sort())
        assert False # TODO: implement your test here

    def test_creation(self):
        pass

    def test_add_action_returns_time(self):
        self.assertEqual(0.1, action_table.addAction(0.1, None, None))

if __name__ == '__main__':
    unittest.main()
