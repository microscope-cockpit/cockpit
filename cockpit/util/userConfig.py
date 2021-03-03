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

import os
import os.path
import pprint

from cockpit.util import logger

## @package userConfig
# This module handles loading and saving changes to user configuration, which
# is used to remember individual users' settings (and a few global settings)
# for dialogs and the like.

## In-memory version of the config; program singleton.
_config = {}
_config_path = ''


## Open the config file and unserialize its contents.
def _loadConfig(fpath):
    config = {}
    try:
        with open(fpath, 'r') as fh:
            config = eval(fh.read())
    except FileNotFoundError:
        config = {}
    except SyntaxError as e:
        logger.log.error("invalid or corrupted user config file '%s': %s",
                         fpath, str(e))
    return config


## Serialize the current config state for the specified user
# to the appropriate config file.
def _writeConfig(config, fpath):
    ## Use pprint instead of pickle to write the config files so that
    ## their contents are readable.
    printer = pprint.PrettyPrinter()
    if not printer.isreadable(config):
        raise RuntimeError('user config file has non-writable data')

    dirname = os.path.dirname(fpath)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(fpath, 'w') as fh:
        fh.write(printer.pformat(config))


def clearAllValues() -> None:
    """Discard all previous configuration and writes that to file."""
    global _config
    global _config_path
    _config = {}
    _writeConfig(_config, _config_path)


## Retrieve the config value referenced by key.
# If key is not found, default is inserted and returned.
# If the value changed as a result of the lookup (because we wrote the
# default value to config), then write config back to the file.
def getValue(key, default=None):
    global _config
    global _config_path
    try:
        result = _config[key]
    except KeyError:
        _config[key] = default
        _writeConfig(_config, _config_path)
        result = default
    return result

## Set the entry referenced by key to the given value. Users are set as
# in getValue.
def setValue(key, value):
    global _config
    global _config_path
    _config[key] = value
    _writeConfig(_config, _config_path)


def initialize(cockpit_config):
    global _config
    global _config_path
    _config_path = os.path.join(cockpit_config['global'].get('config-dir'),
                                'config.py')
    _config = _loadConfig(_config_path)
