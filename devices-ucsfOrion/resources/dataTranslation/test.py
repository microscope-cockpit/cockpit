import ctypes
import numpy
import time

foo = ctypes.cdll.LoadLibrary('dt_wrapper.dll')
foo.translateError.restype = ctypes.c_char_p


def initialize():
    error = foo.initialize()
    if error:
        print "Error initializing:",foo.translateError(error)


def setVoltage(channel, voltage):
    voltage = ctypes.c_float(voltage)
    foo.setVoltage(0, voltage)


def cleanup():
    foo.cleanup()


def ramp(channel, start, stop, wait):
    for voltage in numpy.arange(start, stop, (stop - start) / 10.0):
        setVoltage(channel, voltage)
        time.sleep(wait)

def sin(channel, amplitude, wait, repeats):
    for i in xrange(repeats):
        for theta in numpy.arange(0, numpy.pi * 2, numpy.pi / 12):
            setVoltage(channel, amplitude * (numpy.sin(theta) + 1))
            time.sleep(wait)
