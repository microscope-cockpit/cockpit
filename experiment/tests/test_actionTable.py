import unittest
from actionTable import ActionTable

class TestActionTable(unittest.TestCase):
    def test___getitem__(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.__getitem__(index))
        assert False # TODO: implement your test here

    def test___init__(self):
        # action_table = ActionTable()
        assert False # TODO: implement your test here

    def test___len__(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.__len__())
        assert False # TODO: implement your test here

    def test___repr__(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.__repr__())
        assert False # TODO: implement your test here

    def test___setitem__(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.__setitem__(index, val))
        assert False # TODO: implement your test here

    def test_addAction(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.addAction(time, handler, parameter))
        assert False # TODO: implement your test here

    def test_addToggle(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.addToggle(time, handler))
        assert False # TODO: implement your test here

    def test_clearBadEntries(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.clearBadEntries())
        assert False # TODO: implement your test here

    def test_enforcePositiveTimepoints(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.enforcePositiveTimepoints())
        assert False # TODO: implement your test here

    def test_getFirstAndLastActionTimes(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.getFirstAndLastActionTimes(canUseCache))
        assert False # TODO: implement your test here

    def test_getLastActionFor(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.getLastActionFor(handler))
        assert False # TODO: implement your test here

    def test_prettyString(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.prettyString(handlers))
        assert False # TODO: implement your test here

    def test_shiftActionsBack(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.shiftActionsBack(markTime, delta))
        assert False # TODO: implement your test here

    def test_sort(self):
        # action_table = ActionTable()
        # self.assertEqual(expected, action_table.sort())
        assert False # TODO: implement your test here

    def test_creation(self):
        action_table = ActionTable()
#Makesureitdoesn'traiseanyexceptions.

    def test_add_toggle_raises_type_error_for_handler_equal_None_and_time_equal_01(self):
        action_table = ActionTable()
        self.assertRaises(TypeError, lambda: action_table.addToggle(0.1, None))

    def test_add_action_returns_time_for_handler_equal_None_and_parameter_equal_None_and_time_equal_01(self):
        action_table = ActionTable()
        self.assertEqual(0.1, action_table.addAction(0.1, None, None))

if __name__ == '__main__':
    unittest.main()
