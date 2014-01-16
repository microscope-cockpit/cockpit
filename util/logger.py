import util.files

import logging
import os
import sys
import time

## @package logger
# This file contains code for setting up our logger, as well as the logger
# itself.

## Logger instance
log = None

## Generate a filename to store logs in; specific to the specified username.
def generateLogFileName(user = ''):
    filename = 'MUI_'
    filename = os.path.join(util.files.getLogDir(), filename)
    filename += time.strftime("%Y%m%d_%a-%H%M")
    if user:
        filename += '_%s' % user
    filename += '.log'
    return filename


## Global current log handle.
curLogHandle = None

## Start logging under the specified username (or none if no user is available
# yet).
def makeLogger(user = ''):
    global log
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    filename = generateLogFileName(user)

    global curLogHandle
    curLogHandle = logging.FileHandler(filename, mode = "a")
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(module)10s:%(lineno)4d  %(message)s')
    curLogHandle.setFormatter(formatter)
    curLogHandle.setLevel(logging.DEBUG)
    log.addHandler(curLogHandle)


## Switch from the current logfile to a new one, presumably because the user
# has now logged in.
def changeFile(newFilename):
    log.debug("close logging file, open newfile '%s'", newFilename)
    curLogHandle.stream.close()
    curLogHandle.baseFilename = newFilename
    curLogHandle.stream = open(newFilename, curLogHandle.mode)
    

