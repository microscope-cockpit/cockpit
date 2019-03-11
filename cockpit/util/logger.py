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


import cockpit.util.files

import logging
import os.path
import time

## @package logger
# This file contains code for setting up our logger, as well as the logger
# itself.

## Logger instance
log = None

def makeLogger():
    """Create the logger and instantiate the ``log`` singleton.
    """
    global log
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    filename = 'MUI_' +  time.strftime("%Y%m%d_%a-%H%M") + '.log'
    filepath = os.path.join(cockpit.util.files.getLogDir(), filename)

    log_handler = logging.FileHandler(filepath, mode = "a")
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(module)10s:%(lineno)4d  %(message)s')
    log_handler.setFormatter(formatter)
    log_handler.setLevel(logging.DEBUG)

    log.addHandler(log_handler)
