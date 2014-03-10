import depot
import device
import events
import gui.guiUtils
import handlers.imager
import handlers.lightPower
import handlers.lightSource
import microManager
import util.colors

import ctypes
import os
import re
import time
import wx

CLASS_NAME = 'LightsDevice'



## This controls which lasers and light sources are used. It's a bit complex
# because lasers are determined by filters, and thus are mutually-exclusive 
# (you can't have two lasers that each make it past the same notch filter).
# We also provide the DIA and EPI light sources, with their own complexities
# in setting filter positions.
# Frankly, some of the code in this module is a real mess. You have my
# apologies. It's a tangled system with a lot of interlocking dependencies.
class LightsDevice(device.Device):
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
        ## Indicates if we've turned the 561 laser on yet this session.
        self.haveEnabled561 = False

        ## List of (name, wavelength) tuples for non-laser lightsources.
        self.specialLights = [('DIA', 0), ('EPI Blue', 405),
                ('EPI Cyan', 440), ('EPI Green', 514),
                ('EPI Yellow', 580), ('EPI Red', 640)]

        ## Maps EPI light source labels to the (EPI filter,
        # TIFilterBlock1 filter, TIFilterBlock2 filter) positions for those
        # labels.
        self.labelToEpiConfigs = {
            'EPI Blue': (1, 5, 5),
            'EPI Cyan': (4, 0, 4),
            'EPI Green': (5, 1, 0),
            'EPI Yellow': (9, 0, 0),
            'EPI Red': (6, 3, 0),
        }

        ## Dropdown menu for the first filter turret.
        self.filterMenu1 = None
        ## Dropdown menu for the second filter turret.
        self.filterMenu2 = None
        ## Dropdown menu for the EPI mode.
        self.epiMenu = None


    def initialize(self):
        mmDevice = depot.getDevice(microManager)
        self.core = mmDevice.getCore()
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment', self.onExperimentCleanup)
        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        events.subscribe('nikon: prepare for image', self.prepareForImage)


    ## Expose a UI for setting the filters.
    def makeUI(self, parent):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        columnSizer = wx.BoxSizer(wx.VERTICAL)
        columnSizer.Add(wx.StaticText(parent, -1, "Filter turret 1:"))
        self.filterMenu1 = wx.Choice(parent, -1,
                choices = self.core.getAllowedPropertyValues('TIFilterBlock1', 'Label'))
        self.filterMenu1.SetStringSelection(
                self.core.getProperty('TIFilterBlock1', 'Label'))
        self.filterMenu1.Bind(wx.EVT_CHOICE,
                lambda event: self.setFilter(True, self.filterMenu1.GetStringSelection()))
        columnSizer.Add(self.filterMenu1)
        sizer.Add(columnSizer)
        
        columnSizer = wx.BoxSizer(wx.VERTICAL)
        columnSizer.Add(wx.StaticText(parent, -1, "Filter turret 2:"))
        self.filterMenu2 = wx.Choice(parent, -1,
                choices = self.core.getAllowedPropertyValues('TIFilterBlock2', 'Label'))
        self.filterMenu2.SetStringSelection(
                self.core.getProperty('TIFilterBlock2', 'Label'))
        self.filterMenu2.Bind(wx.EVT_CHOICE,
                lambda event: self.setFilter(False, self.filterMenu2.GetStringSelection()))
        columnSizer.Add(self.filterMenu2)
        sizer.Add(columnSizer, 0, wx.LEFT, 5)

        return sizer


    ## Save our settings to the provided dict.
    def onSaveSettings(self, settings):
        settings['Filter turrets'] = [self.filterMenu1.GetStringSelection(),
                self.filterMenu2.GetStringSelection()]


    ## Load settings from the provided dict.
    def onLoadSettings(self, settings):
        if 'Filter turrets' in settings:
            self.setFilter(True, settings['Filter turrets'][0])
            self.setFilter(False, settings['Filter turrets'][1])


    def getHandlers(self):
        result = []
        labels = self.core.getAllowedPropertyValues('TIFilterBlock1', 'Label')
        nameAndWavelength = []
        # Hack: extract the wavelength from the label, if possible.
        # Generate a nicer name for the laser lights too.
        for label in labels:
            # HACK: ignore the "3-D-FTx" option.
            if label == '3-D-FTx':
                continue
            match = re.match('.*?-(\d+)(.*)', label)
            if not match:
                wavelength = label
                name = label
            else:
                wavelength = int(match.group(1))
                name = match.group(1) + match.group(2)
            nameAndWavelength.append((name, wavelength))
            self.nameToMMName[name] = label

        for name, wavelength in nameAndWavelength + self.specialLights:
            handler = handlers.lightSource.LightHandler(
                name, "%s light source" % name,
                {'setEnabled': self.setEnabled,
                 'setExposureTime': self.setExposureTime,
                 'getExposureTime': self.getExposureTime,
                 'setExposing': self.setExposing}, wavelength, 100)
            result.append(handler)
            self.nameToExposureTime[handler.name] = 100
            self.nameToHandler[handler.name] = handler
            # Special behavior for lasers: add a power control.
            if (name, wavelength) not in self.specialLights:
                # Add a laser power handler for the lasers with valid wavelengths,
                # and default the laser to 15% emission.
                color = util.colors.wavelengthToColor(wavelength)
                powerHandler = handlers.lightPower.LightPowerHandler(
                    name + ' power', "%s light source" % name,
                    {'setPower': self.setPower}, wavelength, 0, 100, 15,
                    color, units = '%'
                )
                result.append(powerHandler)
                self.nameToHandler[powerHandler.name] = powerHandler
                # HACK: only lasers get tracked in self.wavelengths and
                # self.wavelengthToName!
                self.wavelengths.append(wavelength)
                self.wavelengthToName[wavelength] = handler.name
        self.wavelengths.sort()
        return result


    ## Set all laser power to 15% to avoid blinding people.
    def finalizeInitialization(self):
        for wavelength in self.wavelengths:
            self.setPower(self.wavelengthToName[wavelength], 15)


    ## A light source is being enabled. We handle this in different ways
    # depending on the type of light source being switched.
    # Handle switching between DIA, EPI, and laser-based illumination.
    def setEnabled(self, name, isEnabled):
        if 'DIA' in name:
            self.enableDia(name, isEnabled)
        elif 'EPI' in name:
            self.enableEpi(name, isEnabled)
        else:
            self.enableLaser(name, isEnabled)


    ## Enable/disable a laser: adjust the AOM and dichroics.
    def enableLaser(self, name, isEnabled):
        wavelength = self.nameToHandler[name].wavelength
        if isEnabled == (wavelength in self.activeWavelengths):
            # No-op; trying to enable an already-on laser, or disable an
            # already-off laser.
            return

        if isEnabled:
            # HACK: if this is the 561 laser and it's the first time it's
            # been enabled this session, remind the user to push the button
            # on the laser box.
            if wavelength == 561 and not self.haveEnabled561:
                self.haveEnabled561 = True
                gui.guiUtils.showHelpDialog(None,
                        "Remember to push the button corresponding to the " +
                        "561 laser on the front of the Spectral laser " +
                        "control box, if this is the first time you have " +
                        "used the 561 laser since powering on the box.")
            # Disable all DIA/EPI light sources that are active.
            for name, handler in self.nameToHandler.iteritems():
                if 'DIA' in name or 'EPI' in name:
                    handler.setEnabled(False)                

        # Add/remove things from self.activeWavelengths.
        if not isEnabled:
            if wavelength in self.activeWavelengths:
                self.activeWavelengths.remove(wavelength)
        else:
            self.activeWavelengths.add(wavelength)


    ## Prepare for an image to be taken with the specified light source(s).
    # We need to set the dichroics appropriately.
    def prepareForImage(self, lights):
        # We can only handle one type of light at a time (laser/DIA/EPI).
        shutterMode = None
        ourHandlers = self.nameToHandler.values()
        for light in lights:
            if light not in ourHandlers:
                # We don't care about this light source.
                continue
            lightType = None
            if 'DIA' in light.name:
                lightType = 'Shutter-DIA'
            elif 'EPI' in light.name:
                lightType = 'Shutter-EPI'
            elif light.wavelength in self.wavelengthToName:
                lightType = 'LMM5-Shutter'
            if shutterMode is not None and shutterMode != lightType:
                raise RuntimeError("Tried to take an image with both %s and %s light types at the same time; I can only have one shutter active at a time." % (lightType, shutterMode))
            shutterMode = lightType

        if shutterMode is None:
            print "No important lights out of",lights
            # No lights we care about.
            return

        print "Have shutter more",shutterMode

        # Set the shutter mode.
        self.core.setShutterDevice(shutterMode)
        events.publish('MM shutter change', shutterMode)

        # Adjust the filter turrets, only if using laser or EPI lights.
        if shutterMode == 'LMM5-Shutter':
            # Construct a list of lights that are lasers, since we don't
            # care about the others (e.g. LEDs).
            laserLights = []
            for light in lights:
                if light.wavelength in self.wavelengths:
                    laserLights.append(light)
            print "Laser lights are",laserLights
            if len(laserLights) == 1:
                # Just one light; set the appropriate filter.
                activeWavelength = laserLights[0].wavelength
                activeName = self.wavelengthToName[activeWavelength]
                self.setFilter(True, self.nameToMMName[activeName])
            elif laserLights:
                # Multiple lasers; set the "3-D-FTx" filter which seems
                # to be empty.
                self.setFilter(True, '3-D-FTx')
                # Print a warning about the AOM.
                print "Multiple simultaneous active lasers! I don't know if the AOM will work well for this..."

            # Construct the necessary AOM setting from the wavelengths of
            # the active lights.
            modeStrings = []
            for handler in sorted(laserLights, key = lambda l: l.wavelength):
                wavelength = handler.wavelength
                index = self.wavelengths.index(wavelength) + 1
                # HACK: the 440 laser shows up as a 444 in the LMM5 control
                # for some reason.
                if wavelength == 440:
                    wavelength = 444
                modeStrings.append('%dnm-%d' % (wavelength, index))
            print "Mode strings are",modeStrings
            self.core.setProperty('LMM5-Shutter', 'Label', 
                    '/'.join(modeStrings))
        elif shutterMode == 'Shutter-EPI':
            # Set the dichroics appropriate for the selected EPI mode.
            epiLights = []
            for light in lights:
                if 'EPI' in light.name:
                    epiLights.append(light)
            if len(epiLights) > 1:
                raise RuntimeError("Tried to take an image with multiple simultaneous EPI lights; this is not possible. Suggest you set a different emission filter for each one.")
            epiPosition, filter1, filter2 = self.labelToEpiConfigs[light.name]
            filter1Label = self.core.getAllowedPropertyValues('TIFilterBlock1', 'Label')[filter1]
            filter2Label = self.core.getAllowedPropertyValues('TIFilterBlock2', 'Label')[filter2]
            self.core.setProperty('Wheel-EPI', 'Label',
                    'Filter-%d' % epiPosition)
            self.setFilter(True, filter1Label)
            self.setFilter(False, filter2Label)
            

    ## Enable/disable the DIA light source. If enabling, disable all others
    # and set the shutter mode.
    def enableDia(self, name, isEnabled):
        if isEnabled:
            for name, handler in self.nameToHandler.iteritems():
                if (handler.deviceType == depot.LIGHT_TOGGLE and 
                        'DIA' not in name):
                    handler.setEnabled(False)
            

    ## Enable/disable the EPI light source. If enabling, disable all non-EPI
    # lights and set the shutter mode.
    def enableEpi(self, name, isEnabled):
        if isEnabled:
            for name, handler in self.nameToHandler.iteritems():
                if (handler.deviceType == depot.LIGHT_TOGGLE and 
                        'EPI' not in name):
                    handler.setEnabled(False)
                    

    ## Set one of the filters, and update our UI to match.
    def setFilter(self, isFirstFilter, label, shouldBlock = True):
        name = ['TIFilterBlock1', 'TIFilterBlock2'][not isFirstFilter]
        # Cast to string, away from UTF.
        self.core.setProperty(name, 'Label', str(label))
        if isFirstFilter:
            self.filterMenu1.SetStringSelection(label)
        else:
            self.filterMenu2.SetStringSelection(label)
        if shouldBlock:
            self.core.waitForDevice(name)


    ## Return True if any of our active lights are in self.specialLights.
    def haveActiveSpecialLights(self):
        for light in self.activeWavelengths:
            if light in self.specialLights:
                return True
        return False


    ## Change the exposure time for a light source.
    def setExposureTime(self, name, time):
        self.nameToExposureTime[name] = time


    ## Get the exposure time for a light source.
    def getExposureTime(self, name):
        return self.nameToExposureTime[name]


    ## Set a light source to continuous exposure.
    def setExposing(self, name, isOn):
        self.setEnabled(name, isOn)
        if isOn:
            # Set up the dichroics appropriately.
            # \todo This will act as if only one of our lights can be
            # in continuous-exposure mode at a time...which is honestly
            # probably true for most (all?) lights.
            self.prepareForImage([self.nameToHandler[name]])
        self.core.setShutterOpen(isOn)


    ## Set the laser power for the specific laser.
    def setPower(self, name, power):
        wavelength = self.nameToHandler[name].wavelength
        # Paranoia: tried to set power on a non-laser.
        if wavelength not in self.wavelengths:
            return
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
            self.setEnabled(self.wavelengthToName[wavelength], False)


    ## Cleanup at the end of an experiment: restore our active lasers to what
    # they were before we started.
    def onExperimentCleanup(self, *args):
        # Disable lasers that weren't on before.
        for wavelength in list(self.activeWavelengths):
            if wavelength not in self.cachedWavelengths:
                self.setEnabled(self.wavelengthToName[wavelength], False)
        # Enable lasers that were on before.
        for wavelength in list(self.cachedWavelengths):
            if wavelength not in self.activeWavelengths:
                self.setEnabled(self.wavelengthToName[wavelength], True)

