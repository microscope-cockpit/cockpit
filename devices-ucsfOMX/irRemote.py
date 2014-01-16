import device
import events
import interfaces.stageMover
import util.threads

import numpy
import serial
import struct
import threading
import time

CLASS_NAME = 'IRRemote'

## Maps inputs to directions in which to move.
MOTION_COMMANDS = {
    struct.pack('4b', 64, 0, 0, 8): numpy.array((1, 0, 0)),
    struct.pack('4b', 64, 0, 0, 4): numpy.array((-1, 0, 0)),
    struct.pack('4b', 64, 0, 0,16): numpy.array((0, 1, 0)),
    struct.pack('4b', 64, 0, 0,32): numpy.array((0, -1, 0)),
}



class IRRemote(device.Device):
    def __init__(self):
        device.Device.__init__(self)

        ## Connection to the serial port the IR receiver is connected to.
        self.connection = None


    def initialize(self):
        self.connection = serial.Serial('COM3', 2400, serial.SEVENBITS,
                parity = serial.PARITY_NONE, stopbits = serial.STOPBITS_ONE,
                rtscts = 1, timeout = .1)
        self.processRemote()


    ## Process input from the remote control. We get inputs when a button
    # is pressed and when it is released. Pressing starts motion; releasing
    # ends it.
    @util.threads.callInNewThread
    def processRemote(self):
        amMoving = False
        curCommand = None
        while True:
            try:
                command = self.connection.read(4)
                if command and curCommand:
                    # Stop current motion.
                    events.publish('IR remote stop')
                    curCommand = None
                elif command in MOTION_COMMANDS:
                    # Start motion.
                    delta = MOTION_COMMANDS[command]
                    axis = numpy.where(delta != 0)[0][0]
                    direction = delta[axis]
                    events.publish('IR remote start', axis, direction)
                    curCommand = command
            except Exception, e:
                # Ignore it.
                pass
