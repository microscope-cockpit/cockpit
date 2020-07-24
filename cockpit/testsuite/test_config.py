#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
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

import configparser
import contextlib
import os
import os.path
import posixpath
import tempfile
import unittest
import unittest.mock

import cockpit.config

"""Test units for cockpit.config
"""

def patch_like_linux(func):
    """Decorator to patch cockpit.config to behave like in Linux systems.

    This enables testing cases of Linux on Windows and Mac.
    """
    not_win = unittest.mock.patch('cockpit.config._is_windows', lambda : False)
    not_mac = unittest.mock.patch('cockpit.config._is_mac', lambda : False)
    posix_path = unittest.mock.patch('os.path', posixpath)
    return posix_path(not_mac(not_win(func)))


def patched_env(values):
    """Patch env by adding/replacing variables."""
    return unittest.mock.patch.dict('os.environ', values)


class MockConfigRead:
    """Mocks ``ConfigParser.read`` to record requested filenames."""
    def __init__(self):
        self.reset_mock()

    def reset_mock(self):
        self.filenames = []

    def __call__(self, filenames, encoding=None):
        if isinstance(filenames, (str, bytes, os.PathLike)):
            self.filenames.append(filenames)
        else:
            self.filenames.extend(filenames)


def mock_cockpit_config_read(func):
    return unittest.mock.patch('cockpit.config.CockpitConfig.read',
                               new_callable=MockConfigRead)(func)

def mock_depot_config_read(func):
    return unittest.mock.patch('cockpit.config.DepotConfig.read',
                               new_callable=MockConfigRead)(func)


@contextlib.contextmanager
def patched_config_dirs(system_basedirs, user_basedir):
    """Replace default config dirs"""
    s = unittest.mock.patch('cockpit.config._default_system_config_dirs',
                            lambda : [d.cockpit_basedir
                                      for d in system_basedirs])
    u = unittest.mock.patch('cockpit.config._default_user_config_dir',
                            lambda : user_basedir.cockpit_basedir)
    with s, u:
        yield (s, u)


def call_cockpit(*args):
    return cockpit.config.CockpitConfig(['cockpit', *args])


class TempConfigFile:
    """Create temporary file with specific text content."""
    def __init__(self, content=''):
        self._file = tempfile.NamedTemporaryFile(mode='w')
        self._file.write(content)
        self._file.flush()

    @property
    def path(self):
        return self._file.name


class TempConfigBaseDir:
    """Create config directory structure with depot and cockpit files"""
    def __init__(self, cockpit_conf={}, depot_conf={}):
        self._basedir = tempfile.TemporaryDirectory()

        os.mkdir(self.cockpit_basedir)
        self._write_config(self.cockpit_filepath, cockpit_conf)
        self._write_config(self.depot_filepath, depot_conf)

    @property
    def path(self):
        return self._basedir.name

    @property
    def cockpit_basedir(self):
        return os.path.join(self.path, 'cockpit')

    @property
    def cockpit_filepath(self):
        return os.path.join(self.cockpit_basedir, 'cockpit.conf')

    @property
    def depot_filepath(self):
        return os.path.join(self.cockpit_basedir, 'depot.conf')

    def _write_config(self, filepath, config_dict):
        config = configparser.ConfigParser()
        config.read_dict(config_dict)
        with open(filepath, 'w') as fh:
            config.write(fh)

    def __del__(self):
        ## Very silly.  TemporaryDirectory will raise ResourceWarning
        ## for implicitely cleaning up unless via context manager.  If
        ## we don't use it a context manager, we need to explicitely
        ## cleanup after ourselves or our tests get full of warnings.
        self._basedir.cleanup()


class TestConfigConverters(unittest.TestCase):
    def setUp(self):
        self.config = configparser.ConfigParser(converters=
                                                cockpit.config._type_converters)


class TestGetType(TestConfigConverters):
    def assertTypes(self, class_name, expected_type):
        self.config.read_dict({'sect' : {'opt' : class_name}})
        self.assertEqual(self.config.gettype('sect', 'opt'),
                         expected_type)

    def test_builtin_type(self):
        self.assertTypes('str', str)

    def test_python_stdlib_type(self):
        import decimal
        self.assertTypes('decimal.Decimal', decimal.Decimal)

    def test_cockpit_device_type(self):
        import cockpit.devices.light
        self.assertTypes('cockpit.devices.light.SimpleLight',
                          cockpit.devices.light.SimpleLight)


class TestGetPath(TestConfigConverters):
    def assertPath(self, value, env, expected_expansion):
        self.config.read_dict({'sect' : {'opt' : value}})
        with patched_env(env):
            self.assertEqual(self.config.getpath('sect', 'opt'),
                             expected_expansion)

    def test_expandvars(self):
        self.assertPath('$FOO/bar', {'FOO' : '/foo'}, '/foo/bar')

    def test_tilde_in_expanded_var(self):
        """Tilde expansion happens before variable expansion.

        Tilde expansion must occur before variable expansion, so if
        the variable has a tilde, the tilde should not get expanded.
        """
        self.assertPath('$FOO/bar', {'FOO' : '~'}, '~/bar')


class TestGetPaths(TestConfigConverters):
    def assertPaths(self, value, paths):
        txt = ('[sec]\n'
               'opt = %s' % (value))
        self.config.read_string(txt)
        self.assertListEqual(self.config.getpaths('sec', 'opt'), paths)

    def test_multiple_paths(self):
        txt = ('path/to/file1\n'
               '  with whitespace  \n'
               '    /and/trailing whitespace/too  \n'
               '  /path/to/file3\n')
        paths = ['path/to/file1',
                 'with whitespace',
                 '/and/trailing whitespace/too',
                 '/path/to/file3']
        self.assertPaths(txt, paths)

    def test_single_path(self):
        """getpaths() is not confused with single path case"""
        self.assertPaths('path/to/file1\n', ['path/to/file1'])

    def test_empty_lines(self):
        """Empty lines are ignored"""
        txt = ('path/to/file1\n'
               '  \n'
               '  /path/to/file3\n')
        paths = ['path/to/file1', '/path/to/file3']
        self.assertPaths(txt, paths)


class TestGetLines(TestConfigConverters):
    def assertLines(self, value, lines):
        txt = ('[sec]\n'
               'opt = %s' % (value))
        self.config.read_string(txt)
        self.assertListEqual(self.config.getlines('sec', 'opt'), lines)

    def test_whitespace(self):
        """Trailing and leading whitespace, and empty lines are removed"""
        txt = ('foo bar \n'
               '  \n'
               '  qux\n')
        lines = ['foo bar', 'qux']
        self.assertLines(txt, lines)


@patch_like_linux
class TestLinuxPaths(unittest.TestCase):
    def assertConfigDirs(self, env_value, expected):
        with patched_env({'XDG_CONFIG_DIRS' : env_value}):
            observed = cockpit.config.default_system_cockpit_config_files()
        self.assertListEqual(observed, expected)

    def test_multiple_config_dirs(self):
        self.assertConfigDirs('/a:/c:/b',
                              ['/a/cockpit/cockpit.conf',
                               '/c/cockpit/cockpit.conf',
                               '/b/cockpit/cockpit.conf'])

    def test_ignoring_empty_path_entry(self):
        """Ignore empty paths in XDG_CONFIG_DIRS"""
        self.assertConfigDirs(':/a:/c/d::/b:',
                              ['/a/cockpit/cockpit.conf',
                               '/c/d/cockpit/cockpit.conf',
                               '/b/cockpit/cockpit.conf'])

    def test_empty_xdg_variable(self):
        """Ignore set but empty XDG_CONFIG_DIRS variable"""
        self.assertConfigDirs('', ['/etc/xdg/cockpit/cockpit.conf'])

    def test_default_without_xdg_variables(self):
        """Default files and directories in Linux systems"""
        with patched_env({'HOME' : '/srv/people'}):
            for var in ('XDG_CONFIG_DIRS', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'):
                os.environ.pop(var, None)
            self.assertEqual(cockpit.config.default_system_cockpit_config_files(),
                             ['/etc/xdg/cockpit/cockpit.conf'])
            self.assertEqual(cockpit.config.default_system_depot_config_files(),
                             ['/etc/xdg/cockpit/depot.conf'])
            self.assertEqual(cockpit.config.default_user_cockpit_config_files(),
                             ['/srv/people/.config/cockpit/cockpit.conf'])
            self.assertEqual(cockpit.config.default_user_depot_config_files(),
                             ['/srv/people/.config/cockpit/depot.conf'])
            self.assertEqual(cockpit.config._default_log_dir(),
                             '/srv/people/.cache/cockpit')
            self.assertEqual(cockpit.config._default_user_config_dir(),
                             '/srv/people/.config/cockpit')


class TestConfigReading(unittest.TestCase):
    """Test what config files are read under different conditions.

    This is done by mocking the read method and record the filenames.
    Ideally we should check what configuration we obtain at the end of
    the process, not which files get read and under what order.
    However, that's tricky because it would require us to patch the
    functions that figure what files should be read which is the thing
    we want to test here.  Such case should be handled by integration
    tests.
    """

    def assertFilesRead(self, read_mock, files):
        """
        Args:
            read_mock: instance of our :class:``MockConfigRead``
            files: list of our :class:``TempConfigFile``
        """
        self.assertEqual(read_mock.filenames, [f.path for f in files])

    @mock_depot_config_read
    @mock_cockpit_config_read
    def test_default_reads_files(self, cockpit_read_mock, depot_read_mock):
        """There are system and user files read by default.

        This is not so much a test that we care about directly but it
        is an assumption on many other config tests.  When we test
        that certain options add/prevent files from being read, we are
        assuming that the default list of read files is not empty.  So
        test that.
        """
        call_cockpit()
        read_files = {
            'cockpit' : {
                'all' : cockpit_read_mock.filenames,
                'user' : [],
                'system' : [],
            },
            'depot' : {
                'all' : depot_read_mock.filenames,
                'user' : [],
                'system' : [],
            },
        }

        for group, option in (('system', '--no-user-config-files'),
                              ('user', '--no-system-config-files')):
            cockpit_read_mock.reset_mock()
            depot_read_mock.reset_mock()
            call_cockpit(option)
            read_files['cockpit'][group] = cockpit_read_mock.filenames
            read_files['depot'][group] = depot_read_mock.filenames

        for files in read_files.values():
            for group in ('all', 'user', 'system'):
                self.assertTrue(len(files[group]) > 0)
            self.assertEqual(files['all'], files['system'] + files['user'])

    @mock_depot_config_read
    @mock_cockpit_config_read
    def test_skip_all_config_files(self, cockpit_read_mock, depot_read_mock):
        """--no-config-files prevents files from being read"""
        call_cockpit('--no-config-files')
        self.assertFilesRead(cockpit_read_mock, [])
        self.assertFilesRead(depot_read_mock, [])

    @mock_depot_config_read
    @mock_cockpit_config_read
    def test_skip_user_and_system(self, cockpit_read_mock, depot_read_mock):
        """--no-system-config-files and --no-user-config-files together"""
        call_cockpit('--no-system-config-files', '--no-user-config-file')
        self.assertFilesRead(cockpit_read_mock, [])
        self.assertFilesRead(depot_read_mock, [])

    @mock_depot_config_read
    def test_depot_file(self, depot_read_mock):
        """--depot-file prevents default from being read"""
        depot_config = TempConfigFile()
        call_cockpit('--depot-file', depot_config.path)
        self.assertFilesRead(depot_read_mock, [depot_config])

    @mock_depot_config_read
    def test_depot_files_ignored_in_config_file(self, depot_read_mock):
        """depot-files in --config-file is ignored if --depot-file is set

        Depot conf files specified via command line don't just have
        their values overload those on the cockpit files.  If they are
        specified on command line then no other gets read, not even
        those mentioned on cockpit config files specified via command
        line.
        """
        file_tmp = TempConfigFile()
        config_file = TempConfigFile('[global]\n'
                                     'depot-files = %s\n'
                                     % (file_tmp.path))
        cmd_tmp = TempConfigFile()
        call_cockpit('--no-config-files',
                     '--depot-file', cmd_tmp.path,
                     '--config-file', config_file.path)
        self.assertFilesRead(depot_read_mock, [cmd_tmp])

    @mock_depot_config_read
    @mock_cockpit_config_read
    def test_setting_files_to_read(self, cockpit_read_mock, depot_read_mock):
        """--no-config-files does not skip files set via command line"""
        depot1 = TempConfigFile()
        depot2 = TempConfigFile()
        cockpit1 = TempConfigFile()
        cockpit2 = TempConfigFile()
        call_cockpit('--no-config-files',
                     '--config-file', cockpit1.path,
                     '--config-file', cockpit2.path,
                     '--depot-file', depot1.path,
                     '--depot-file', depot2.path)
        self.assertFilesRead(cockpit_read_mock, [cockpit1, cockpit2])
        self.assertFilesRead(depot_read_mock, [depot1, depot2])


class TestCockpitConfigPrecedence(unittest.TestCase):
    """Precedence of all methods to specify cockpit config files.

    We shouldn't test the order that the files are read because that's
    not what we care about.  What we care about is the option values
    at the end of reading all files.  The relationship between a final
    option value and the file read order is an implementation detail.

    To do this we have 5 options named 'a' to 'e' and have 5 files,
    each with a subset of those options set to their name.  We can
    test the precedence by checking the final value of each option.
    """
    def setUp(self):
        def create_options(value, options):
            return {option: value for option in options}
        self.sys1 = TempConfigBaseDir({'sec' : create_options('sys1', 'abcde')})
        self.sys2 = TempConfigBaseDir({'sec' : create_options('sys2', 'abcd')})
        self.user = TempConfigBaseDir({'sec' : create_options('user', 'abc')})
        self.cmd1 = TempConfigBaseDir({'sec' : create_options('cmd1', 'ab')})
        self.cmd2 = TempConfigBaseDir({'sec' : create_options('cmd2', 'a')})

    def assertOptionsOrigin(self, config, origins):
        """Check the origin of the value for each option in config.

        Args:
            config (``CockpitConfig``):
            origins (dict<str:str>): keys are the file/origin. Each
                character of the value is the option name.
        """
        for expected_origin, options in origins.items():
            for option in options:
                origin = config['sec'][option]
                if origin != expected_origin:
                    raise AssertionError("option '%s' was '%s' instead of '%s"
                                         % (option, origin, expected_origin))
        for option, value in config['sec'].items():
            if option not in origins[value]:
                raise AssertionError("option '%s' should have not been '%s'"
                                     % (option, value))

    def test_basic(self):
        """Simplest case, one system-wide file and user config"""
        with patched_config_dirs([self.sys1], self.user):
            config = call_cockpit()
        self.assertOptionsOrigin(config, {'user' : 'abc',
                                          'sys1' : 'de'})

    def test_multiple_system(self):
        """Precedence with multiple system-wide files"""
        with patched_config_dirs([self.sys2, self.sys1], self.user):
            config = call_cockpit()
        self.assertOptionsOrigin(config, {'user' : 'abc',
                                          'sys1' : 'e',
                                          'sys2' : 'd'})

        with patched_config_dirs([self.sys1, self.sys2], self.user):
            config = call_cockpit()
        self.assertOptionsOrigin(config, {'user' : 'abc',
                                          'sys1' : 'de',
                                          'sys2' : ''})

    @patch_like_linux
    def test_xdg_config_precedence(self):
        """Multiple files in XDG_CONFIG_DIRS are read in the right order.

        Test that the order in XDG_CONFIG_DIRS integrates correctly
        with the rest of the config parsing.
        """
        with patched_env({'XDG_CONFIG_DIRS' : self.sys2.path+':'+self.sys1.path,
                         'XDG_CONFIG_HOME' : self.user.path}):
            config = call_cockpit()
        self.assertOptionsOrigin(config, {'user' : 'abc',
                                          'sys1' : 'e',
                                          'sys2' : 'd'})

    def test_ignore_user(self):
        with patched_config_dirs([self.sys1], self.user):
            config = call_cockpit('--no-user-config-files')
        self.assertOptionsOrigin(config, {'user' : '',
                                          'sys1' : 'abcde'})

    def test_system_user(self):
        with patched_config_dirs([self.sys1], self.user):
            config = call_cockpit('--no-system-config-files')
        self.assertOptionsOrigin(config, {'user' : 'abc',
                                          'sys1' : ''})

    def test_all(self):
        """Precedence with multiple system-wide, user, and command line"""
        with patched_config_dirs([self.sys2, self.sys1], self.user):
            config = call_cockpit('--config-file', self.cmd1.cockpit_filepath,
                                  '--config-file', self.cmd2.cockpit_filepath)
        self.assertOptionsOrigin(config, {'cmd2' : 'a',
                                          'cmd1' : 'b',
                                          'user' : 'c',
                                          'sys2' : 'd',
                                          'sys1' : 'e'})


class TestDepotConfig(unittest.TestCase):
    def test_duplicated_devices_separate_files(self):
        """Duplicated devices on separate files raise an exception."""
        file1 = TempConfigFile('[device]\n'
                               'foo: bar\n')
        file2 = TempConfigFile('[device]\n'
                               'qux: bar\n')
        with self.assertRaises(configparser.DuplicateSectionError):
            call_cockpit('--no-config-files',
                         '--depot-file', file1.path,
                         '--depot-file', file2.path)

    def test_read(self):
        """Depot files are read and merged."""
        file1 = TempConfigFile('[dev1]\n'
                               'type: bar\n'
                               'foo: qux\n')
        file2 = TempConfigFile('[dev2]\n'
                               'type: foo\n'
                               'bar: grob\n')
        config = call_cockpit('--no-config-files',
                              '--depot-file', file1.path,
                              '--depot-file', file2.path)
        depot = config.depot_config
        self.assertEqual(dict(depot['dev1']), {'type': 'bar', 'foo': 'qux'})
        self.assertEqual(dict(depot['dev2']), {'type': 'foo', 'bar': 'grob'})

    def test_depot_files_option(self):
        """Files in depot-files cockpit config option take precedence

        If there is a depot-files option defined in a cockpit config
        file, even those read by default, then that value takes
        precedence and the default depot.conf files are no longer
        read.
        """
        file_depot = TempConfigFile('[Bar]\ntype: bar\nfrom: config-file\n')
        user = TempConfigBaseDir({'global': {'depot-files': file_depot.path}},
                                 {'Foo': {'type': 'foo', 'from': 'user'}})
        with patched_config_dirs([], user):
            depot = call_cockpit().depot_config
        self.assertNotIn('Foo', depot)
        self.assertIn('Bar', depot)
        self.assertEqual(depot['Bar'].get('from'), 'config-file')

    def test_read_files(self):
        """Keeps information what files were actually read.

        With so many methods to control what files get read, we need
        to keep in memory which files were actually read.  And this is
        those that were actually read, not those that we tried to
        read.
        """
        existing_file = TempConfigFile()
        with tempfile.TemporaryDirectory() as existing_dir:
            missing_file = os.path.join(existing_dir, 'missing.conf')
            depot = cockpit.config.DepotConfig([existing_file.path,
                                                missing_file])
        self.assertEqual(depot.files, [existing_file.path])
        self.assertNotIn(missing_file, depot.files)

    def test_interpolation_only_once(self):
        """Files in depot config do not go through multiple interpolations.

        Because we manually add config sections from multiple
        ConfigParser instances, we need to be careful to not go
        through two interpolation steps.
        """
        conf_file = TempConfigFile('[filters]\n'
                                   'filters:\n'
                                   '  0, ND 1%%\n'
                                   '  1, ND 10%%\n')
        depot = cockpit.config.DepotConfig(conf_file.path)
        self.assertEqual(depot['filters'].get('filters'),
                         '\n0, ND 1%\n1, ND 10%')


class TestCommandLineOptions(unittest.TestCase):
    def test_debug(self):
        ## Also get the default to make sure this test is not passing
        ## just because something else is making debug the default.
        config_default = call_cockpit('--no-config-files')
        config_debug = call_cockpit('--no-config-files', '--debug')
        self.assertEqual(config_debug['log']['level'], 'debug')
        self.assertNotEqual(config_default['log']['level'], 'debug')


if __name__ == '__main__':
    unittest.main()
