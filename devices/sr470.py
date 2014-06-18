""" Cockpit device for SRS SR470 shutter controller.

Mick Phillips, 2014.
Largely derived from Chris' delayGen device.
"""

import depot
import device
import events
import handlers.executor
import handlers.lightSource
import util.logger
import decimal
import re
import telnetlib

CLASS_NAME = 'StanfordShutterDevice'

class StanfordShutterDevice(device.Device):
	def __init__(self):
		device.Device.__init__(self)
		self.isActive = True
