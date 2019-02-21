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

import errno
import os
import os.path
import pprint

from . import files
from . import logger

## @package userConfig
# This module handles loading and saving changes to user configuration, which
# is used to remember individual users' settings (and a few global settings)
# for dialogs and the like.

## In-memory version of the config; program singleton.
_config = {}


## Open the config file and unserialize its contents.
def _loadConfig(fpath):
    config = {}
    try:
        with open(fpath, 'r') as fh:
            config = eval(fh.read())
    except IOError as e:
        ## Python2 does not have FileNotFoundError, hence this
        if e.errno == errno.ENOENT:
            pass
    except SyntaxError as e:
        logger.log.error("invalid or corrupted user config file '%s': %s",
                         fpath, str(e))
    return config


## Serialize the current config state for the specified user
# to the appropriate config file.
def _writeConfig(config):
    ## Use pprint instead of pickle to write the config files so that
    ## their contents are readable.
    printer = pprint.PrettyPrinter()
    if not printer.isreadable(config):
        raise RuntimeError('user config file has non-writable data')

    config_fpath = _getConfigPath()
    if not os.path.exists(os.path.dirname(config_fpath)):
        os.makedirs(os.path.basedir(config_fpath))

    with open(config_fpath, 'w') as fh:
        fh.write(printer.pformat(config))


def _getConfigPath():
    return os.path.join(files.getConfigDir(), 'config.py')


## Retrieve the config value referenced by key.
# If key is not found, default is inserted and returned.
# If the value changed as a result of the lookup (because we wrote the
# default value to config), then write config back to the file.
def getValue(key, default=None):
    global _config
    try:
        result = _config[key]
    except KeyError:
        _config[key] = default
        _writeConfig(_config)
        result = default
    return result

## Set the entry referenced by key to the given value. Users are set as
# in getValue.
def setValue(key, value):
    global _config
    _config[key] = value
    _writeConfig(_config)


def initialize():
    global _config
    _config = _loadConfig(_getConfigPath())
