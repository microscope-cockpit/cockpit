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
    a dict of key-value pairs.
"""
from collections import deque
import events
from numbers import Number
import threading
import time
import types


class ValueLogger(object):
    def __init__(self):
        self.historyLength = 500
        self.updatePeriod = 1.
        self.currentValues = {}
        self.series = {}
        self.times = deque(maxlen=self.historyLength)
        
        self.lastTime = 0
        self.loggingThread = threading.Thread(target=self.log)
        self.loggingThread.Daemon = True
        self.loggingThread.start()
        events.subscribe("stage mover", self.onEvent)
        events.subscribe("status update", self.onEvent)


    def onEvent(self, *args):
        """Respond to events that publish loggable values."""
        device = args[0].lstrip('devices.')
        data = args[1]
        if isinstance(data, (Number, types.StringTypes)):
            # single value
            self.currentValues[device] = data
        elif isinstance(data, types.ListType):
            # list of values
            formatstr = '%s-%%.%dd' % (data, len(str(len(data))))
            for (i, d) in enumerate(data):
                key = formatstr % i
                self.currentValues[key] = d
                if key not in self.series:
                    self.series[key] = deque(len(self.times) * [None],
                                             maxlen=self.historyLength)
        elif isinstance(data, types.DictionaryType):
            # dict of key, value pairs
            for (key, value) in data.iteritems():
                key = '%s-%s' % (device, key)
                self.currentValues[key] = value
                if key not in self.series:
                    self.series[key] = deque(len(self.times) * [None],
                                             maxlen=self.historyLength)
        else:
            # could not handle this data type
            errStr = '%s could not handle data of type %s from %s' % (
                    type(self), type(data), device)
            raise Exception(errStr)


    def log(self):
        """Loop and log values at specified time interval."""
        t0 = time.time()
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
            self.times.append(now - t0)
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