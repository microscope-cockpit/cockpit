import unittest
import mock
import util.logger
import os
import time

class TestLogging_genfilename(unittest.TestCase):

    def test_generateLogFileName_empty_user_path(self):
        '''Test that the path inthe filename is the one given by util.files.'''
        dir = 'PATH'
        util.logger.util.files.getLogDir = lambda: dir
        filename = util.logger.generateLogFileName()
        path, timestamp, datestamp = filename.split('.')[0].split('_')
        self.assertEqual(path, dir+'/MUI')


    def test_generateLogFileName_empty_user_time(self):
        '''Test that the datestamp matches the format string.'''
        filename = util.logger.generateLogFileName()
        path, timestamp, datestamp = filename.split('.')[0].split('_')
        self.assertTrue( time.strptime(timestamp+'_'+datestamp,
                                       "%Y%m%d_%a-%H%M") )


    def test_generateLogFileName_user(self):
        '''Test the name of the logged in user is added to the log file name.'''
        filename = util.logger.generateLogFileName('user')
        path, timestamp, datestamp, username = filename.split('.')[0].split('_')
        self.assertEqual(username, 'user')


class TestLogging_makeLogger(unittest.TestCase):

    def setUp(self):
        util.logger.logging = mock.Mock(name='logger')
        util.logger.generateLogFileName = lambda _: 'logpath'
        self.logMock = util.logger.logging

    def tearDown(self):
        util.logger.log = None
        util.logger.curLogHandle = None

    def test_makes_logger(self):
        '''Test that a logger is created.'''
        util.logger.makeLogger()
        self.assertTrue(self.logMock.getLogger.called)

    def test_opens_correct_file(self):
        '''Test that a logger is created, and does not overwrite logs.'''
        util.logger.makeLogger()
        self.logMock.FileHandler.assert_any_call('logpath', mode='a')

class TestLogging_changeFile(unittest.TestCase):

    def setUp(self):
        util.logger.log = mock.Mock(name='logger')
        util.logger.curLogHandle = mock.Mock(name='filehandle')

    def tearDown(self):
        util.logger.log = None
        util.logger.curLogHandle = None

    def test_change_file(self):
        vars(util.logger)['open'] = mock.Mock(name='open')

        util.logger.changeFile('newFile')
        self.assertEqual(util.logger.curLogHandle.baseFilename, 'newFile')

        vars(util.logger)['open'] = open
