#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
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

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


import numpy
import os
import sys
import wx

import depot

## @package util.files
# This module contains file-related functions and constants. By default,
# files are stored in C: (obviously only valid for Windows computers); if
# a Configurator handler is available then its values for dataDirectory,
# logDirectory, and configDirectory will be used instead.

## Default root directory for program output
ROOT_DIR = 'C:' + os.path.sep
## Default directory where user data is stored
DATA_DIR = 'MUI_DATA'
## Default directory where logfiles are stored
LOGS_DIR = 'MUI_LOGS'
## Default directory where user config is stored
CONFIG_DIR = 'MUI_CONFIG'

if 'darwin' in sys.platform:
    # OSX case.
    ROOT_DIR = os.path.expanduser('~')
elif 'win' not in sys.platform:
    # Linux case
    # \todo Is this the correct way to test for a Linux platform?
    ROOT_DIR = os.path.expanduser('~')

## Filenames where experiment result files have been saved
resultFiles = []


## Load directory information from the configuration.
def initialize():
    global DATA_DIR
    global LOGS_DIR
    global CONFIG_DIR
    configurators = depot.getHandlersOfType(depot.CONFIGURATOR)
    if configurators:
        for config in configurators:
            if config.getValue('dataDirectory'):
                DATA_DIR = config.getValue('dataDirectory')
            if config.getValue('logDirectory'):
                LOGS_DIR = config.getValue('logDirectory')
            if config.getValue('configDirectory'):
                CONFIG_DIR = config.getValue('configDirectory')
                

## Get the directory in which all users' directories are located
def getDataDir():
    return DATA_DIR


## Return the directory in which logfiles are stored
def getLogDir():
    return LOGS_DIR


## Return the directory in which user config is stored
def getConfigDir():
    return CONFIG_DIR


def ensureDirectoriesExist():
    for directory in [getDataDir(), getLogDir(), getConfigDir()]:
        if not os.path.exists(directory):
            print ("Making",directory)
            os.makedirs(directory)
            # HACK: ensure there's a dummy user if we just made the data dir.
            if directory == getDataDir():
                os.makedirs(os.path.join(directory, 'New user'))
