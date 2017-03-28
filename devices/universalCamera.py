#!/usr/bin/python
# -*- coding: utf-8
#
# Copyright 2016 Mick Phillips (mick.phillips@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""UniversalCamera device.

Supports cameras which implement the interface defined in 
  microscope.camera.Camera ."""

import decimal
import Pyro4
import wx

import camera
import numpy as np
import events
import gui.device
import gui.guiUtils
import gui.toggleButton
import handlers.camera
import util.listener
import util.threads
import util.userConfig
import re
from gui.device import SettingsEditor
from interfaces.imager import pauseVideo

CLASS_NAME = 'UniversalCameraManager'

# The following must be defined as in handlers/camera.py
(TRIGGER_AFTER, TRIGGER_BEFORE, TRIGGER_DURATION, TRIGGER_SOFT) = range(4)
# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

class UniversalCameraDevice(camera.CameraDevice):
    """A class to control Andor cameras via the pyAndor remote interface."""
    def __init__(self, cam_config):
        # camConfig is a dict with containing configuration parameters.
        super(UniversalCameraDevice, self).__init__(cam_config)
        self.handler = None        
        self.enabled = False
        self.panel = None
        self.config = cam_config
        # Pyro proxy
        self.proxy = Pyro4.Proxy('PYRO:%s@%s:%d' %
                                 ('DeviceServer',
                                   cam_config.get('ipAddress') or cam_config.get('host'),
                                   cam_config.get('port')))
        self.listener = util.listener.Listener(self.proxy,
                                               lambda *args: self.receiveData(*args))
        self.base_transform = cam_config.get('baseTransform') or (0, 0, 0)
        self.path_transform = (0, 0, 0)
        self.settings = {}
        self.cached_settings={}
        self.settings['transform'] = tuple(self.path_transform[i] ^ self.base_transform[i] for i in range(3))
        self.settings_editor = None
        self.defaults = DEFAULTS_NONE
        self.get_all_settings = self.proxy.get_all_settings
        self.get_setting = self.proxy.get_setting
        self.set_setting = self.proxy.set_setting
        self.describe_setting = self.proxy.describe_setting
        self.describe_settings = self.proxy.describe_settings
        try:
            self.updateSettings()
        except:
            pass
        if self.settings.has_key('readout mode'):
            self.modes = self.describe_setting('readout mode')['values']
        else:
            self.modes = None


    def finalizeInitialization(self):
        # Decorate updateSettings. Can't do this from the outset, as camera
        # is initialized before interfaces.imager.
        self.updateSettings = pauseVideo(self.updateSettings)


    def updateSettings(self, settings=None):
        if settings is not None:
            self.proxy.update_settings(settings)
        self.settings.update(self.proxy.get_all_settings())
        events.publish("%s settings changed" % str(self))


    def parseMode(self):
        mode_str = self.settings.get('readout mode', None)
        if mode_str is None:
            return '???'
        mode_re = r'(^|.*[^a-zA-Z0-9])(EM)|((M|m)ult)'
        bit_re = r'([0-9]+[- ]?bit)'
        rate_re = r'([0-9]*\.?[0-9]+ ?[MkG]?Hz).*'

        if re.match(mode_re, mode_str):
            out_str = 'EM'
        else:
            out_str = 'Conv'

        match = re.search(bit_re, mode_str)
        if match:
            out_str += '\n%s' % match.group(1)

        match = re.search(rate_re, mode_str)
        if match:
            out_str += '\n%s' % match.group(1)

        return out_str



    def cleanupAfterExperiment(self):
        """Restore settings as they were prior to experiment."""
        if self.enabled:
            self.updateSettings(self.cached_settings)
            #self.proxy.update_settings(self.settings)
            self.proxy.enable()
        self.handler.exposureMode = self.proxy.get_trigger_type()


    def performSubscriptions(self):
        """Perform subscriptions for this camera."""
        events.subscribe('cleanup after experiment',
                self.cleanupAfterExperiment)
        events.subscribe('objective change',
                self.onObjectiveChange)
        events.subscribe('user login',
                self.onUserLogin)


    def onObjectiveChange(self, name, pixelSize, transform, offset):
        self.updateSettings({'pathTransform': transform})
        # Apply the change now if the camera is enabled.
        if self.enabled:
            self.proxy.update_settings(self.settings)


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        # TODO - migrate defaults to a universalDevice base class.
        if self.defaults != DEFAULTS_PENDING:
            # notrhing to do
            return
        try:
            self.proxy.update_settings(self.settings)
        except Exception as e:
            print e
        else:
            self.defaults = DEFAULTS_SENT


    def onUserLogin(self, username):
        # Apply user defaults on login.
        idstr = self.handler.getIdentifier() + '_SETTINGS'
        defaults = util.userConfig.getValue(idstr, isGlobal=False)
        if defaults is None:
            defaults = util.userConfig.getValue(idstr, isGlobal=True)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.updateSettings(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def getHandlers(self):
        """Return camera handlers."""
        result = handlers.camera.CameraHandler(
                "%s" % self.config.get('label'), "iXon camera",
                {'setEnabled': self.enableCamera,
                 'getImageSize': self.getImageSize,
                 'getTimeBetweenExposures': self.getTimeBetweenExposures,
                 'prepareForExperiment': self.prepareForExperiment,
                 'getExposureTime': self.getExposureTime,
                 'setExposureTime': self.setExposureTime,
                 'getImageSizes': self.getImageSizes,
                 'setImageSize': self.setImageSize,
                 'getSavefileInfo': self.getSavefileInfo,
                 'makeUI': self.makeUI,
                 'softTrigger': self.softTrigger},
                TRIGGER_SOFT) # will be set with value from hardware later
        self.handler = result
        self.handler.addListener(self)
        return result


    @pauseVideo
    def enableCamera(self, name, shouldEnable):
        """Enable the hardware."""
        if not shouldEnable:
            # Disable the camera, if it is enabled.
            if self.enabled:
                self.enabled = False
                self.proxy.disable()
                self.proxy.make_safe()
                self.listener.disconnect()
                return self.enabled

        # Enable the camera
        if self.enabled:
            # Nothing to do.
            return
        self.setAnyDefaults()
        self.updateSettings()
        # Use async call to allow hardware time to respond.
        result = Pyro4.async(self.proxy).enable()
        result.wait(timeout=10)
        #raise Exception("Problem enabling %s." % self.name)
        self.enabled = True
        return self.enabled


    def onEnabledEvent(self, evt=None):
        if self.enabled:
            self.handler.exposureMode = self.proxy.get_trigger_type()
            self.listener.connect()


    def onPyroError(self, err, *args):
        """Handle exceptions raised by aync. proxy."""
        raise err


    def getExposureTime(self, name=None, isExact=False):
        """Read the real exposure time from the camera."""
        # Camera uses times in s; cockpit uses ms.
        t = self.proxy.get_exposure_time()
        if isExact:
            return decimal.Decimal(t) * (decimal.Decimal(1000.0))
        else:
            return t * 1000.0


    def getImageSize(self, name):
        """Read the image size from the camera."""
        rect = self.proxy.get_roi()
        return rect[-2:]


    def getImageSizes(self, name):
        """Return a list of available image sizes."""
        return []


    def getSavefileInfo(self, name):
        """Return an info string describing the measurement."""
        #return "%s: %s image" % (name, self.imageSize)
        return ""


    def getTimeBetweenExposures(self, name, isExact=False):
        """Get the amount of time between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started, in milliseconds."""
        # Camera uses time in s; cockpit uses ms.
        t = self.proxy.get_cycle_time() * 1000.0
        if isExact:
            result = decimal.Decimal(t)
        else:
            result = t
        return result


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


    def receiveData(self, *args):
        """This function is called when data is received from the hardware."""
        (image, timestamp) = args
        if not isinstance(image, Exception):
            events.publish('new image %s' % self.name, image, timestamp)
        else:
            # Handle the dropped frame by publishing an empty image of the correct
            # size. Use the handler to fetch the size, as this will use a cached value,
            # if available.
            events.publish('new image %s' % self.name,
                           np.zeros(self.handler.getImageSize(), dtype=np.int16),
                           timestamp)
            raise image


    def setExposureTime(self, name, exposureTime):
        """Set the exposure time."""
        # Camera uses times in s; cockpit uses ms.
        self.proxy.set_exposure_time(exposureTime / 1000.0)


    def setImageSize(self, name, imageSize):
        pass



    def softTrigger(self, name=None):
        self.proxy.soft_trigger()


    ### UI functions ###
    def makeUI(self, parent):
        # TODO - this should probably live in a base deviceHandler.
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        modeButton = gui.device.Button(parent=self.panel,
                                            label=self.parseMode(),
                                            leftAction=self.onModeButton,
                                            rightAction=None,
                                            size=gui.device.TALL_SIZE)
        modeButton.update(self.parseMode)
        events.subscribe("%s settings changed" % self, modeButton.update)
        sizer.Add(modeButton)

        gainButton = gui.device.Button(parent=self.panel,
                                              label='Gain',
                                              leftAction=self.onGainButton,
                                              rightAction=None
                                        )
        gainButton.update(lambda: 'Gain:\t%s' % self.settings.get('gain', None))
        events.subscribe("%s settings changed" % self, gainButton.update)
        sizer.Add(gainButton)

        adv_button = gui.device.Button(parent=self.panel,
                                       label='settings',
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def onGainButton(self, evt):
        if not self.settings.get('gain', False):
            return
        desc = self.describe_setting('gain')
        mingain, maxgain = desc['values']
        gain = wx.GetNumberFromUser('Gain', '', 'Set gain', value=self.settings.get('gain', 0),
                                    min=mingain, max=maxgain)
        if gain == -1:
            return
        self.updateSettings({'gain': gain})


    def onModeButton(self, evt):
        menu = wx.Menu()
        if not self.modes:
            # Camera not enabled yet.
            menu.Append(0, str('No modes known - camera never enabled.'))
            wx.EVT_MENU(self.panel, 0, None)
        else:
            menuID = 0
            for index, mode in enumerate(self.modes):
                menu.Append(menuID, mode)
                wx.EVT_MENU(self.panel, menuID, lambda event, m=index:
                            self.setReadoutModeByIndex(m))
                menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    @pauseVideo
    def setReadoutModeByIndex(self, index):
        self.proxy.set_readout_mode(self.modes[index])
        self.updateSettings()


    def showSettings(self, evt):
        click_pos = wx.GetMousePosition()
        if not self.settings_editor:
            self.settings_editor = SettingsEditor(self, handler=self.handler)
            self.settings_editor.Show()
        self.settings_editor.SetPosition(click_pos)
        self.settings_editor.Raise()


class UniversalCameraManager(camera.CameraManager):
    _CAMERA_CLASS = UniversalCameraDevice
    _SUPPORTED_CAMERAS = 'universalCamera'
