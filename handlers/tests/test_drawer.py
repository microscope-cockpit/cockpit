import unittest
import mock

import handlers.drawer


class testDrawer(unittest.TestCase):

    def setUp(self):
        self.args = {'name':'Drawer', 'groupName':'group'}


    @mock.patch('handlers.drawer.wx')
    def test_makeUI_noCallbacks(self, wxmock):
        self.args['callbacks'] = {'dummy':1}
        drawer = handlers.drawer.DrawerHandler(**self.args)
        ret = drawer.makeUI(mock.Mock(name='windowParent'))

        self.assertEqual(ret, None)


    @mock.patch('handlers.drawer.wx')
    def test_makeUI_noCallbacks(self, wxmock):
        '''Test that wx is correctly instructed to add frames and sizers.'''
        self.args['settings'] = []
        drawer = handlers.drawer.DrawerHandler(**self.args)
        ret = drawer.makeUI(mock.Mock(name='windowParent'))
        self.assertTrue(wxmock.Frame.called)
        self.assertEqual(ret, None)


    @mock.patch('handlers.drawer.events')
    def test_makeInitialPubs_withCallbacks(self, mockevents):
        self.args['callbacks'] = {'dummy':1}
        drawer = handlers.drawer.DrawerHandler(**self.args)
        ret = drawer.makeInitialPublications()

        mockevents.publish.assert_called_with('drawer change', drawer)


    @mock.patch('handlers.drawer.events')
    def test_makeInitialPubs_noCallbacks(self, mockevents):
        self.args['settings'] = mock.MagicMock()
        self.args['settingIndex'] = 0
        drawer = handlers.drawer.DrawerHandler(**self.args)
        ret = drawer.makeInitialPublications()

        mockevents.publish.assert_called_with('drawer change', drawer)


    def test_addCamera_callbacks(self):
        drawer = handlers.drawer.DrawerHandler(**self.args)
        filter_ = {'dye':'DAPI', 'wavelength':555}
        drawer.addCamera('cam', [filter_])
