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

import time
import threading
import sys
try:
    from collections.abc import Iterable
except:
    from collections import Iterable
from datetime import datetime
from cockpit.util import files
import os
DELIMITER = ';'

class ValueLogger:
    _fhs = [] # A list of all filehandles opened in this session.

    def __init__(self, name, keys=None):
        """Initialize a ValueLogger.
        :param filename: logfile for output
        :param keys: keys that name fetched values; used in header
        """
        self._fhLock = threading.Lock()
        self.keys = keys
        filename = name + "_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"
        self.setLogFile(os.path.join(files.getLogDir(), filename)) # sets self._fh


    def __del__(self):
        self._fh.close()


    def setLogFile(self, filename):
        """Open a file and store file handle."""
        fh = open(filename, 'a')
        if self.keys and fh.tell() == 0:
            # Write header at top of new file
            if isinstance(self.keys, Iterable):
                fh.write("timestamp" + DELIMITER + DELIMITER.join([str(k) for k in self.keys]) + "\n")
            else:
                fh.write("timestamp" + DELIMITER + str(self.keys) + "\n")
        # Use __condition to lock file IO while we set the file handle.
        with self._fhLock:
            self._fh = fh
        ValueLogger._fhs.append(self._fh)


    def log(self, values, timestamp=None):
        """Log values to the file.

        :param values: a single value or list of values
        :param  timestamp: a datetime object or None
        """
        if timestamp:
            try:
                ts = timestamp.isoformat()
            except:
                ts =  timestamp
        else:
            ts = datetime.now().isoformat()
        if isinstance(values, Iterable):
            self._fh.write(ts + DELIMITER + DELIMITER.join([str(v) for v in values]) + "\n")
        else:
            self._fh.write(ts + DELIMITER + str(values) + "\n")
        self._fh.flush()


    @classmethod
    def getLogFiles(cls):
        """Return the full path to all files opened in this session."""
        from os import path
        return [path.realpath(fh.name) for fh in cls._fhs]


class PollingLogger(ValueLogger):
    def __init__(self, name, dt, getValues, keys=None):
        """Initialise a PollingValueLogger.
        :param filename: logfile for output
        :param dt: polling interval in seconds
        :param getValues: a callable to fetch a value or values to log
        :param keys: keys that name fetched values; used in header
        """
        super().__init__(name, keys)
        self.dt = dt
        self.getValues = getValues

        self.__condition = threading.Condition()
        self.__stopEvent = threading.Event()

        self.tNext = time.time() + self.dt
        self.__worker = threading.Thread(target=self.__work, name="Logger: %s" % name)
        self.__worker.daemon = True
        self.__worker.start()


    def setPeriod(self, dt):
        """Set polling period, updating tNext and notifying worker thread.
        :param dt:   polling period in seconds
        """
        with self.__condition:
            self.tNext = self.tNext - self.dt + dt
            self.dt = dt
            self.__condition.notify()


    def poll(self):
        """Poll for and log values."""
        self.tNext = time.time() + self.dt
        ts = datetime.now()
        values = self.getValues()
        self.log(values, ts)


    def __work(self):
        """Worker thread target: periodically poll and log values."""
        while not self.__stopEvent.isSet():
            self.__condition.acquire()
            if self.__condition.wait(self.tNext - time.time()):
                # Woken early - something changed.
                continue
            try:
                self.poll()
            except Exception as e:
                sys.stderr.write(e)


class TestSource:
    def __init__(self, name="ValueLoggerTest", dt=15):
        self.logger = PollingLogger(name, dt, self.getValues,
                                    keys=['ch'+str(i) for i in range(4)])
        print("Logging to %s" % self.logger.getLogFiles())


    def getValues(self):
        import random
        return[i+random.random() for i in range(4)]
