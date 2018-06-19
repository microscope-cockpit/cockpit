#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
    

