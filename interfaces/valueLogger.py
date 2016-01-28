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
import datetime
import events
from numbers import Number
import random
import threading
import time
import types


class ValueLoggerTestSource(object):
    def __init__(self):
        self.thread = threading.Thread(target=self.generateValues)
        self.thread.Daemon = True
        self.thread.start()


    def generateValues(self):
        while True:
            value = random.random()
            events.publish("status update", self.__class__.__name__, value)
            time.sleep(1)


class ValueLogger(object):
    """A class to log arbitrary cockpit data."""
    def __init__(self):
        global instance
        instance = self
        ## Maximum no. of points for each dataset.
        self.historyLength = 500
        ## Time between updates in seconds.
        self.updatePeriod = 1.
        ## Current data values.
        self.currentValues = {}
        ## Logged data series.
        self.series = {}
        #filehandle for loggin to file
        self.filehandle = None
        ## Time points for logged data series.
        self.times = deque(maxlen=self.historyLength)
        ## Last time at which point added to series.
        self.lastTime = 0
        ## A thread to perform the logging.
        self.loggingThread = threading.Thread(target=self.log)
        self.loggingThread.Daemon = True
        self.loggingThread.start()
        # Subscribe to position updates.
        events.subscribe("stage mover", self.onMover)
        # Subscribe to device status updates.
        events.subscribe("status update", self.onEvent)


    def onEvent(self, *args):
        """Respond to events that publish loggable values."""
        ## The device that published the event
        device = args[0].split('devices.')[-1]

        ## The data published with the event.
        data = args[1]
        if isinstance(data, (Number, types.StringTypes)):
            # Data is a single value. Map device name to data.
            self.currentValues[device] = data
            if device not in self.series:
                self.series[device] = deque(len(self.times) * [None],
                                            maxlen=self.historyLength)
            #output value to logfile with timestamp
            if filehandle is not None:
                timestamp=datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                filehandle.write(timepstamp+', '+data)
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
        elif data is None:
            ## Device has published 'None': data for this device is
            # no longer current, so update the currentValues dict.
            # Don't use iterkeys, because we don't maintain a lock
            # on the dict so its size could change resulting in a 
            # runtime error.
            keys = [k for k in self.currentValues.keys() 
                    if k.startswith(device + ':')]
            for k in keys:
                self.currentValues[k] = None
        else:
            # Could not handle this data type: raise an exception.
            errStr = '%s could not handle data of type %s from %s' % (
                    type(self), type(data), device)
            raise Exception(errStr)


    def onMover(self, *args):
        """Respond to updates from movers."""
        # Device label = stage mover name + axis
        device = args[0].lstrip('012 ') + ':' + str(args[1])
        data = args[2]
        self.onEvent(device, data)


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
