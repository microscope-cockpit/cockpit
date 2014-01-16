import depot
import device
import events
import handlers.imager
import handlers.lightPower
import handlers.lightSource
import microManager
import util.colors

import ctypes
import os
import re
import time

CLASS_NAME = 'LasersDevice'



## This controls which lasers are used. It's a bit complex because lasers are
# determined by filters, and thus are mutually-exclusive.
class LasersDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # We must initialize after the microManager module.
        self.priority = 1000
        ## MMCorePy object, same as in the microManager module.
        self.core = None
        ## Maps lightsource names to their exposure times.
        self.nameToExposureTime = dict()
        ## Maps lightsource names to their handlers.
        self.nameToHandler = dict()
        ## Maps lightsource names to the names MicroManager uses.
        self.nameToMMName = dict()
        ## Maps wavelengths to lightsource names.
        self.wavelengthToName = dict()
        ## Sorted list of wavelengths we control.
        self.wavelengths = []
        ## Set of active wavelengths.
        self.activeWavelengths = set()
        ## Cached active wavelengths from before an experiment starts.
        self.cachedWavelengths = set()


    def initialize(self):
        mmDevice = depot.getDevice(microManager)
        self.core = mmDevice.getCore()
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment', self.onExperimentCleanup)


    def getHandlers(self):
        result = []
        for label in self.core.getAllowedPropertyValues('TIFilterBlock1', 'Label'):
            # HACK: extract the wavelength from the label, if possible.
            match = re.match('.*?-(\d+)(.*)', label)
            if not match:
                wavelength = label
                name = label
            else:
                wavelength = int(match.group(1))
                name = match.group(1) + match.group(2)
            handler = handlers.lightSource.LightHandler(
                name, "%s light source" % name,
                {'setEnabled': self.setEnabled,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime,
                 'setExposing': self.setExposing}, wavelength, 100)
            self.nameToExposureTime[handler.name] = 100
            self.nameToHandler[handler.name] = handler
            self.nameToMMName[handler.name] = label
            self.wavelengthToName[wavelength] = handler.name
            result.append(handler)
            # Add a laser power handler for the lasers with valid wavelengths.
            if wavelength != label:
                color = util.colors.wavelengthToColor(wavelength)
                handler = handlers.lightPower.LightPowerHandler(
                    name + ' power', "%s light source" % name,
                    {'setPower': self.setPower}, wavelength, 0, 100, 15,
                    color, units = '%'
                )
                self.nameToHandler[handler.name] = handler
                self.wavelengths.append(wavelength)
                result.append(handler)
        self.wavelengths.sort()
        return result


    ## A laser is being enabled; set the excitation filter and the AOM
    # shutter to the appropriate modes.
    def setEnabled(self, name, isEnabled):
        wavelength = self.nameToHandler[name].wavelength
        if isEnabled == (wavelength in self.activeWavelengths):
            # No-op; trying to enable an already-on laser, or disable an
            # already-off laser.
            return
        if not isEnabled:
            if wavelength in self.activeWavelengths:
                self.activeWavelengths.remove(wavelength)
        elif wavelength in self.wavelengths:
            self.activeWavelengths.add(wavelength)
        if len(self.activeWavelengths) == 1:
            # Just one light; set the appropriate filter.
            self.core.setProperty('TIFilterBlock1', 'Label', self.nameToMMName[name])
        elif self.activeWavelengths:
            # Multiple lasers, but there's no multi-wavelength filters
            # (nor an "empty" filter), so just print a warning.
            print "Multiple lasers (%s) active; emission filter will probably block some of them!" % self.activeWavelengths

        if self.activeWavelengths:
            # Enable the laser shutter, and set the AOM shutter to the
            # appropriate mode.
            self.core.setShutterDevice('LMM5-Shutter')
            events.publish('MM shutter change', 'LMM5-Shutter')
            modeStrings = []
            for wavelength in sorted(self.activeWavelengths):
                index = self.wavelengths.index(wavelength) + 1
                # HACK: the 440 laser shows up as a 444 in the LMM5 control
                # for some reason.
                if wavelength == 440:
                    wavelength = 444
                modeStrings.append('%dnm-%d' % (wavelength, index))
            self.core.setProperty('LMM5-Shutter', 'Label', 
                    '/'.join(modeStrings))


    ## Change the exposure time for a light source.
    def setExposureTime(self, name, time):
        self.nameToExposureTime[name] = time


    ## Get the exposure time for a light source.
    def getExposureTime(self, name):
        return self.nameToExposureTime[name]


    ## Set a laser to continuous exposure.
    def setExposing(self, name, isOn):
        self.core.setShutterOpen(isOn)


    ## Set the laser power for the specific laser.
    def setPower(self, name, power):
        wavelength = self.nameToHandler[name].wavelength
        index = self.wavelengths.index(wavelength) + 1
        # HACK: the 440 laser shows up as a 444 in the LMM5 control
        # for some reason.
        if wavelength == 440:
            wavelength = 444
        self.core.setProperty('LMM5-Hub',
                'Transmission (%%) %dnm-%d' % (wavelength, index),
                power)


    ## Prepare for an experiment: "deactivate" all lasers and cache them for
    # later.
    def onPrepareForExperiment(self, *args):
        self.cachedWavelengths = set(self.activeWavelengths)
        # Disable all active lasers, to create a clean slate for the
        # experiment to work with.
        for wavelength in list(self.activeWavelengths):
            print "Disabling",wavelength,"prior to experiment"
            self.setEnabled(self.wavelengthToName[wavelength], False)


    ## Cleanup at the end of an experiment: restore our active lasers to what
    # they were before we started.
    def onExperimentCleanup(self, *args):
        print "Want to restore",self.activeWavelengths,"to",self.cachedWavelengths
        # Disable lasers that weren't on before.
        for wavelength in list(self.activeWavelengths):
            if wavelength not in self.cachedWavelengths:
                self.setEnabled(self.wavelengthToName[wavelength], False)
        # Enable lasers that were on before.
        for wavelength in list(self.cachedWavelengths):
            if wavelength not in self.activeWavelengths:
                self.setEnabled(self.wavelengthToName[wavelength], True)

