'''
User uses a file-based data structure for storing users - I guess this is
mockable by overriding os?
'''

import unittest
import imp
import mock
from mockManagers import mock_import


class test_user(unittest.TestCase):

    def setUp(self):
        with mock_import(['events', 'files', 'gui', 'gui.loggingWindow',
                          'gui.mainWindow', 'gui.mosaic', 'gui.mosaic.window',
                          'util.logger', 'util.userConfig', 'wx']) as mocks:
            import util.user
            imp.reload(util.user)
            self.mocks = mocks
        self.user = util.user


    def test_login_presents_dialog(self):
        '''Login shoud present a dialog to the user.'''
        self.user.getUsers = lambda: []
        self.user.login(None)
        self.assertTrue(self.mocks['wx'].SingleChoiceDialog.called)


    def test_login_sends_user_name(self):
        '''Login should publish a event when a name is selected.'''
        self.user.getUsers = lambda: []

        dialog = mock.Mock()
        dialog.GetStringSelection.return_value = 'user'
        self.mocks['wx'].SingleChoiceDialog.return_value = dialog

        self.user.login(None)
        self.mocks['events'].publish.assert_called_with("user login", 'user')


    def test_login_changes_logging_file(self):
        '''Check that the login process rotates the logs correctly.'''
        self.user.getUsers = lambda: []

        dialog = mock.Mock()
        dialog.GetStringSelection.return_value = 'user'
        self.mocks['util.logger'].generateLogFileName = lambda s: s
        self.mocks['wx'].SingleChoiceDialog.return_value = dialog
        self.user.login(None)

        self.mocks['util.logger'].changeFile.assert_called_with('user')
