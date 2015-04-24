"""interfaces.valueLogger

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================

Logs values published by devices.
Devices should publish a 'status update' event, with a device
identifier and one of:
    a single value;
    a list of values;
    a dict of key-value pairs.
The logger will store a finite history of these values, and the history
is displayed in an isntance of gui.valueLogger.ValueLoggerWindow.
"""
from collections import deque
import events
from numbers import Number
import threading
import time
import types
import datetime


class ValueLogger(object):
    """A class to log arbitrary cockpit data."""
    def __init__(self):
        ## Maximum no. of points for each dataset.
        self.historyLength = 500
        ## Time between updates in seconds.
        self.updatePeriod = 1.
        ## Current data values.
        self.currentValues = {}
        ## Logged data series.
        self.series = {}
        ## Time points for logged data series.
        self.times = deque(maxlen=self.historyLength)
        ## Last time at which point added to series.
        self.lastTime = 0
        ## A thread to perform the logging.
        self.loggingThread = threading.Thread(target=self.log)
        self.loggingThread.Daemon = True
        self.loggingThread.start()
        # Subscribe to position updates.
        events.subscribe("stage mover", self.onEvent)
        # Subscribe to device status updates.
        events.subscribe("status update", self.onEvent)


    def onEvent(self, *args):
        """Respond to events that publish loggable values."""
        ## The device that published the event
        device = args[0].lstrip('devices.')
        ## The data published with the event.
        data = args[1]
        if isinstance(data, (Number, types.StringTypes)):
            # Data is a single value. Map device name to data.
            self.currentValues[device] = data
        elif isinstance(data, types.ListType):
            # Data is a list of values. Map device name and integer to data.
            formatstr = '%s:%%.%dd' % (data, len(str(len(data))))
            for (i, d) in enumerate(data):
                key = formatstr % i
                self.currentValues[key] = d
                if key not in self.series:
                    self.series[key] = deque(len(self.times) * [None],
                                             maxlen=self.historyLength)
        elif isinstance(data, types.DictionaryType):
            # Data is a dict of key, value pairs. Map device name and key to values.
            for (key, value) in data.iteritems():
                key = '%s:%s' % (device, key)
                self.currentValues[key] = value
                if key not in self.series:
                    self.series[key] = deque(len(self.times) * [None],
                                             maxlen=self.historyLength)
        else:
            # Could not handle this data type: raise an exception.
            errStr = '%s could not handle data of type %s from %s' % (
                    type(self), type(data), device)
            raise Exception(errStr)


    def log(self):
        """Loop and log values at specified time interval."""
        while True:
            now = time.time()
            if not self.series:
                # self.series is still empty
                time.sleep(self.updatePeriod)
                continue
            if now < self.lastTime + self.updatePeriod:
                # self.updateperiod has not elapsed since last logging
                time.sleep(0.1)
                continue
            # Log current values and time.
            self.times.append(datetime.datetime.fromtimestamp(now))
            self.lastTime = now
            for key, series in self.series.iteritems():
                series.append(self.currentValues.get(key, None))
            events.publish("valuelogger update", None)


def initialize():
    """Create the ValueLogger."""
    global instance
    instance = ValueLogger()


def makeInitialPublications():
    # Nothing to do here.
    pass