import unittest
import mock

import handlers.lightFilter


class testLightFilter(unittest.TestCase):

    def setUp(self):
        self.args = {'name':'name', 'groupName':'grpname', 'wavelength':555,
                     'filterAmounts':mock.MagicMock(), 'color':'green',
                     'curPosition':1, 'numGlobals':1}

    def test_init(self):
        filterhandler = handlers.lightFilter.LightFilterHandler(**self.args)

    @mock.patch('handlers.lightFilter.events')
    def test_makeInitialPublications_noGlobals(self, mockevents):
        filterhandler = handlers.lightFilter.LightFilterHandler(**self.args)
        filterhandler.makeInitialPublications()
        self.assertEqual(mockevents.publish.call_args_list, [])

    @mock.patch('handlers.lightFilter.events')
    def test_makeInitialPublications_Globals(self, mockevents):
        self.args['globalIndex'] = 1
        filterhandler = handlers.lightFilter.LightFilterHandler(**self.args)
        filterhandler.makeInitialPublications()
        mockevents.publish.assert_called_with('global filter change', 1, 1)

    @mock.patch('handlers.lightFilter.wx')
    @mock.patch('handlers.lightFilter.util')
    @mock.patch('handlers.lightFilter.events')
    def test_selectPosition_announces_filter_change(self, mockevents, mockutil, mockwx):
        self.args['globalIndex'] = 1
        self.args['callbacks'] = mock.MagicMock()
        filterhandler = handlers.lightFilter.LightFilterHandler(**self.args)
        filterhandler.selectPosition()
        mockevents.publish.assert_called_with('global filter change', 1, 1)

    @mock.patch('handlers.lightFilter.wx')
    @mock.patch('handlers.lightFilter.util')
    @mock.patch('handlers.lightFilter.events')
    def test_selectPosition_saves_user_config(self, mockevents, mockutil, mockwx):
        self.args['globalIndex'] = 1
        self.args['callbacks'] = mock.MagicMock()
        filterhandler = handlers.lightFilter.LightFilterHandler(**self.args)
        filterhandler.selectPosition()
        mockutil.userConfig.setValue.assert_called_with('name-filterPosition', 1)
