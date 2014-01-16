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
            print "Making",directory
            os.makedirs(directory)
            # HACK: ensure there's a dummy user if we just made the data dir.
            if directory == getDataDir():
                os.makedirs(os.path.join(directory, 'New user'))
