import depot
import device
import handlers.imager
import handlers.lightPower
import handlers.lightSource
import util.colors

import ctypes
import os
import time
import wx

CLASS_NAME = 'LEDsDevice'



class LEDsDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Maps lightsource names to their exposure times.
        self.nameToExposureTime = dict()
        ## Maps lightsource names to the channels on the DAQ we use
        # to control them.
        self.nameToChannel = dict()
        ## Maps lightsource names to their handlers.
        self.nameToHandler = dict()
        ## Maps lightsource names to their output voltage.
        self.nameToVoltage = dict()
        ## Path to the library we use to control the LEDs.
        self.libraryPath = os.path.join('devices', 'resources',
                'dataTranslation', 'dt_wrapper.dll')
        ## Loaded library instance.
        self.library = None
        ## Boolean indicating if we initialized successfully; if not,
        # then that probably means the LEDs have been appropriated
        # for use somewhere else.
        self.haveLEDs = False


    def initialize(self):
        try:
            self.library = ctypes.cdll.LoadLibrary(self.libraryPath)
            self.library.translateError.restype = ctypes.c_char_p
            error = self.library.initialize()
            if error:
                raise RuntimeError(self.library.translateError(error))
            self.haveLEDs = True
        except Exception, e:
            dialog = wx.MessageDialog(parent = None,
                    message = "The LEDs are not available: %s" % e,
                    caption = "LED error",
                    style = wx.OK | wx.CANCEL | wx.ICON_EXCLAMATION)
            if dialog.ShowModal() == wx.ID_CANCEL:
                # Abort startup.
                events.publish('program startup failure', 'LED initialization', e)
                


    def getHandlers(self):
        if not self.haveLEDs:
            # Couldn't initialize the LEDs, so nothing to be done here.
            return []
        result = []
        for label, wavelength, channel in [
                ('650 LED', 650, 0),
                ('750 LED', 750, 1)]:
            # Set up lightsource handlers. Default to 100ms exposure time.
            handler = handlers.lightSource.LightHandler(
                label, "%s light source" % label, 
                {'setEnabled': lambda *args: None,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime,
                 'setExposing': self.setExposing}, wavelength, 100)
            self.nameToExposureTime[handler.name] = 100
            self.nameToChannel[handler.name] = channel
            self.nameToHandler[handler.name] = handler
            self.nameToVoltage[handler.name] = 1
            result.append(handler)
            # Set up light power handlers. Default to 1V power level.
            color = util.colors.wavelengthToColor(wavelength)
            handler = handlers.lightPower.LightPowerHandler(
                label + ' power', "%s light source" % label,
                {'setPower': self.setPower}, wavelength, 0, 10, 1, color,
                units = 'V')
            result.append(handler)
        result.append(handlers.imager.ImagerHandler(
            'LED imager', 'miscellaneous',
            {
                'takeImage': self.expose
            }
        ))
        return result


    ## Change the exposure time for a light source.
    def setExposureTime(self, name, time):
        self.nameToExposureTime[name] = time


    ## Get the exposure time for a light source.
    def getExposureTime(self, name):
        return self.nameToExposureTime[name]


    ## Set the voltage for the given LightPower handler.
    def setPower(self, name, power):
        # Trim off the " power" from the name.
        name = name.split(' power')[0]
        self.nameToVoltage[name] = power
        self.setVoltage(self.nameToChannel[name], power)


    ## Turn the LED(s) on for their respective illumination times.
    def expose(self):
        # Generate a sorted list of (time, channel) pairs, shortest exposure
        # first.
        pairs = []
        for name, exposureTime in self.nameToExposureTime.iteritems():
            if self.nameToHandler[name].getIsEnabled():
                # Convert exposure time to seconds.
                pairs.append((exposureTime / 1000.0, self.nameToChannel[name]))
                # Turn the LED on.
                self.setVoltage(self.nameToChannel[name], self.nameToVoltage[name])
        pairs.sort()
        startTime = time.time()
        curTime = startTime
        # Wait for each LED to "time out", then turn it off.
        for exposureTime, channel in pairs:
            waitTime = exposureTime - (curTime - startTime)
            if waitTime > 0:
                time.sleep(waitTime)
            self.setVoltage(channel, 0)
            curTime = time.time()


    ## Turn the specified LED on/off and leave it that way.
    def setExposing(self, name, isOn):
        power = self.nameToVoltage[name]
        if not isOn:
            power = 0
        self.setVoltage(self.nameToChannel[name], power)
            

    ## Set the voltage on the specified channel.
    def setVoltage(self, channel, voltage):
        voltage = ctypes.c_float(voltage)
        self.library.setVoltage(channel, voltage)
