'''
User uses a file-based data structure for storing users - I guess this is
mockable by overriding os?
'''

import unittest
import imp
import mock
import os
import wx
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


    def test_logout_publishes_logout(self):
        '''Tests that when the user logs out, the event is published.'''
        self.user.logout(False)
        self.mocks['events'].publish.assert_called_with("user logout")

    @unittest.expectedFailure
    def test_logout_calls_login(self):
        '''If login again, then logout should call login with the parent window.
        '''
        self.user.login = mock.Mock(name='loginMock')
        self.user.logout()
        # element 0 of the first call should be the parent window
        self.assertEqual(type(self.user.login.call_args[0][0] ), type(wx.Window))


class test_user_modification(unittest.TestCase):

    def setUp(self):
        with mock_import(['events', 'files', 'gui', 'gui.loggingWindow',
                          'gui.mainWindow', 'gui.mosaic', 'gui.mosaic.window',
                          'util.logger', 'util.userConfig', 'wx', 'os']) as mocks:
            import util.user
            imp.reload(util.user)
            self.mocks = mocks
            # leave join available, as it is used to provide input to functions
            # we do care about mocking
            mocks['os'].path.join = os.path.join
        self.user = util.user


    def test_createUser(self):
        '''createUser should create a folder in util.files.getDataDir()'''
        self.user.files = mock.Mock()
        self.user.files.getDataDir.return_value = 'pathto'
        self.user.createUser('user')
        self.mocks['os'].mkdir.assert_called_with('pathto/user')


    def test_deleteUser(self):
        '''createUser should remove a folder in util.files.getDataDir()'''
        self.user.files = mock.Mock()
        self.user.files.getDataDir.return_value = 'pathto'
        self.user.deleteUser('user')
        self.mocks['os'].rmdir.assert_called_with('pathto/user')
