import camera
import events
import gui.guiUtils
import gui.toggleButton
import handlers.camera
import util.connection
import util.threads

import collections
import decimal
import numpy
import threading
import time
import wx

from config import CAMERAS

## Describes the settings used to connect a given camera. 
CameraSettings = collections.namedtuple(
    'CameraSettings', ['is16Bit', 'isConventional', 'speed'])
AllowedModes = { 'Conv16\n1MHz': CameraSettings(True, True, 0),
                 'Conv14\n3MHz': CameraSettings(False, True, 0),
                 'EM16\n1MHz': CameraSettings(True, False, 0),
                 'EM14\n10MHz': CameraSettings(False, False, 0),
                 'EM14\n5MHz': CameraSettings(False, False, 1),
                 'EM14\n3MHz': CameraSettings(False, False, 2) }

CLASS_NAME = 'CameraManager'
# Chris Weisiger's code had a boolean for whether or not the camera is
# an iXon+ so assume that this code can either handle an iXon or iXon+.  I
# didn't see anything mentioning the iXon Ultra, so I assume (perhaps
# incorrectly) that this code can not handle that model.
SUPPORTED_CAMERAS = ['ixon', 'ixon_plus']
COLOUR = {'grey': (170, 170, 170),
          'green': (32, 128, 32),
          }


## This module handles communications with our EMCCD camera. Chris Weisiger
# wrote the device handling and commented that it was mostly copied from
# the corresponding OMX code.  I've modified the code structure to make it
# more similar to Oxford's andorCameras.py.  Oxford uses a different remote
# for the Andor cameras so I didn't take the route of replacing this with
# andorCameras.py since I don't know what the consequences will be of
# swapping their remote for the one currently in use.
class AndorEMCCDCameraDevice(camera.CameraDevice):
    def __init__(self, camConfig):
        # camConfig is a dict containing configuration parameters.
        super(AndorEMCCDCameraDevice, self).__init__(camConfig)
        self.config = camConfig
        self.connobj = util.connection.Connection(
            'pyroCam', self.config.get('ipAddress'), self.config.get('port'))
        self.isIxonPlus = self.config.get('model') == 'ixon_plus'
        self.exposureTime = None
        self.timeBetweenExposures = None
        # This is a dummy value.  Should be set from within setImage() before
        # it is ever used.
        self.imageSize = (0, 0)
        ## Last-set exposure time we used.
        self.lastExposureTime = 100
        ## Last-set EM gain we used.
        self.lastEMGain = 0
        ## Last-set camera settings we used.
        self.lastModeLabel = AllowedModes.keys()[0]
        self.lastSettings = AllowedModes[self.lastModeLabel]
        ## Button for the mode setting.
        self.modeButton = None
        ## Button for the EM gain setting.
        self.gainButton = None
        ## Panel containing the above buttons.
        self.panel = None
        ## List of available image readout sizes.
        self.imageSizes = ['Full', '512x256', '512x128']


    def getHandlers(self):
        """Returns the handler for the camera."""
        result = handlers.camera.CameraHandler(
            '%s' % self.config.get('label'), 'iXon camera',
            {'setEnabled': self.enableCamera,
             'getImageSize': self.getImageSize,
             'getTimeBetweenExposures': self.getTimeBetweenExposures,
             'prepareForExperiment': self.prepareForExperiment,
             'getExposureTime': self.getExposureTime,
             'setExposureTime': self.setExposureTime,
             'getImageSizes': self.getImageSizes,
             'setImageSize': self.setImageSize,
             'getSavefileInfo': self.getSavefileInfo},
            handlers.camera.TRIGGER_AFTER)
        return result


    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        self.panel.SetBackgroundColour(COLOUR['grey'])
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(
            self.panel, -1, self.config['label'], size=(128, 24),
            style=wx.ALIGN_CENTER)
        label.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.VERTICAL)

        self.modeButton = gui.toggleButton.ToggleButton(
            label='Mode:\n%s' % self.lastModeLabel,
            parent=self.panel, size=(128,48))
        self.modeButton.Bind(wx.EVT_LEFT_DOWN, self.onModeButton)
        rowSizer.Add(self.modeButton)

        self.gainButton = gui.toggleButton.ToggleButton(
                label = "EM Gain\n%d" % self.lastEMGain,
                parent = self.panel, size = (128, 48))
        self.gainButton.Bind(wx.EVT_LEFT_DOWN, self.onGainButton)
        rowSizer.Add(self.gainButton)

        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def updateUI(self):
        if self.connobj.getIsConnected():
            # Light up the mode button if the camera is active.
            self.modeButton.setActive(True)

            # Light up the gain button if the camera is active and mode
            # uses EM.
            if self.lastSettings.isConventional:
                self.gainButton.setActive(False)
            else:
                self.gainButton.setActive(True)
        else:
            self.modeButton.setActive(False)
            self.gainButton.setActive(False)

        # Labels must be set after setActive call, or the original
        # label persists.
        self.modeButton.SetLabel('Mode:\n%s' % self.lastModeLabel)
        self.gainButton.SetLabel('EM Gain:\n%d' % self.lastEMGain)


    ## Handle the user clicking on the EM gain button. Pop
    # up a menu of possible gain values, including the option
    # to set them on a per-camera basis.
    def onGainButton(self, event = None):
        menu = wx.Menu()
        menuId = 1
        for value in range(0, 255, 10):
            menu.Append(menuId, str(value))
            wx.EVT_MENU(
                self.panel,
                menuId,
                lambda event, value = value: self.setGain(value))
            menuId += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    ## Set the gain for a camera, or for all cameras if none is
    # specified.
    def setGain(self, value):
        self.lastEMGain = value
        if self.connobj.getIsConnected():
            # This will make it pick up the new gain.
            self.resetCamera()
        self.updateUI()


    ## Handle the user clicking on one of the camera mode buttons.
    def onModeButton(self, button):
        menu = wx.Menu()
        menuID = 0
        for modeLabel in AllowedModes.keys():
            menu.Append(menuID, modeLabel)
            wx.EVT_MENU(
                self.panel,
                menuID,
                lambda event, m=modeLabel: self.setAmplifierMode(m))
            menuID += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def setAmplifierMode(self, modeLabel):
        self.lastModeLabel = modeLabel
        self.lastSettings = AllowedModes[modeLabel]
        if self.connobj.getIsConnected():
            # This will apply self.lastSettings.
            self.resetCamera()
        self.flushCache()
        self.updateUI()


    ## Flush any relevant caches we have for the specified camera.
    def flushCache(self):
        self.timeBetweenExposures = None


    ## Receive data from a camera.
    def receiveData(self, action, *args):
        if action == 'new image':
            (image, timestamp) = args
            # Fix image orientations.
            if self.name == 'iXon1':
                image = image.transpose()
            events.publish('new image %s' % self.name, image, timestamp)


    @util.threads.callInNewThread
    def enableCamera(self, name, isOn):
        """Enable or disable the hardware."""
        if isOn:
            self.connobj.connect(lambda *args: self.receiveData(*args))
            # The start() function can take a long time.
            self.connobj.connection._pyroTimeout = 30
            try:
                self.connobj.connection.abort()
            except Exception, e:
                # Camera can't abort, probably because it hasn't been
                # initialized yet; no big deal.
                pass
            thread = gui.guiUtils.WaitMessageDialog(
                    "Connecting to %s" % self.name, "Please wait", .5)
            thread.start()
            try:
                self.connobj.connection.start(self.isIxonPlus)
            except Exception:
                # Something's wrong with the camera; try re-initializing and
                # then reconnecting.
                try:
                    self.connobj.connection.init()
                    self.connobj.connection.start(self.isIxonPlus)
                except Exception, e:
                    thread.shouldStop = True
                    raise e
            thread.shouldStop = True
            self.connobj.connection._pyroTimeout = 3
            self.connobj.connection.settemp(-70)
            self.resetCamera()
        else:
            self.connobj.connection.abort()
            self.connobj.connection.quit()
            self.connobj.disconnect()

        self.updateUI()


    def getTimeBetweenExposures(self, name, isExact = False):
        """Get the amount of time, in milliseconds, between exposures.

        This is the time that must pass after stopping one exposure
        before another can be started.
        """

        if self.timeBetweenExposures is None:
            # Set the cached value.  The exposure time is folded into the
            # readout time for this remote so subtract it off.
            self.timeBetweenExposures = (
                self.connobj.connection.getTimesExpAccKin()[2] -
                self.connobj.connection.getexp())
        val = self.timeBetweenExposures
        if isExact:
            val = decimal.Decimal(val)
        return val


    def setExposureTime(self, name, time):
        """Sets the exposure time, in milliseconds."""
        if (self.exposureTime is not None and
            abs(self.exposureTime - time) < .1):
            # Don't bother; we're already there.
            return
        self.connobj.connection.abort()
        # HACK: for some reason OMXT's iXon camera can't handle short
        # integration times (at 5ms and below you start noticing a major
        # blurring issue in the readout direction), so we don't allow them.
        # This has nothing to do with the *sample* exposure time, of course.
        self.connobj.connection.setExposureTime(max(10, time))
        self.connobj.connection.settrigger(True)
        self.connobj.connection.exposeTillAbort(False)
        self.exposureTime = time
        self.flushCache()


    def getExposureTime(self, name, isExact = False):
        """Reads the camera's exposure time and returns the value, in
        milliseconds."""
        result = self.connobj.connection.getexp()
        if isExact:
            result = decimal.Decimal(result)
        return result


    def getImageSizes(self, name):
        """Returns a list of strings describing available image sizes."""
        return self.imageSizes


    def setImageSize(self, name, size):
        """Sets the image size for the camera.

        Positional parameters:
        name -- Is not used.  Included for compatibility with the old
        arrangment where this object managed multiple cameras index by name.
        size -- Is one of the strings from in the list returned by
        getImageSizes().
        """
        height = None
        yOffset = 0
        if 'x' in size:
            width, height = map(int, size.split('x'))
            yOffset = 256 - height / 2
        self.setImage(height, yOffset, shouldAbort = True)
       

    def getSavefileInfo(self, name):
        """Returns an info string describing the measurement."""
        return "%s: %s gain, %s image" % (
            self.name, self.lastEMGain, self.imageSize)


    def getImageSize(self, name):
        """Read the image size from the camera."""
        return self.imageSize


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment.

        Ensures that it's in frame transfer mode with and exposure time of
        zero (so that getFramerate returns the minimum time between exposures.
        """
        self.connobj.connection.abort()
        if self.connobj.connection.gettemp()[1] > -40:
            # Camera is too warm. 
            raise RuntimeError("Camera temperature is above -40C!")
        self.connobj.connection.setExposureTime(0)
        self.connobj.connection.settrigger(True)
        # Since we'll be in frame-transfer mode, we'll be accumulating light
        # until the next external trigger. This causes a lot of background in
        # the first image. So we'll trigger the first image immediately before
        # starting the experiment (or as close-to as possible) and discard it.
#        self.connobj.connection.skipNextNimages(1)
        self.connobj.connection.exposeTillAbort(1)
        self.flushCache()


    ## Reset the camera to a baseline state.
    def resetCamera(self):
        self.connobj.connection.abort()
        self.connobj.connection.cammode(
            self.lastSettings.is16Bit,
            self.lastSettings.isConventional,
            self.lastSettings.speed,
            self.lastEMGain,
            None)
        self.connobj.connection.setshutter(1)
        self.connobj.connection.settrigger(True)
        self.connobj.connection.setExposureTime(self.lastExposureTime)
        self.setImage()


    ## Set the image shape for the camera. We only vary the height of the
    # image, not the width, since we read pixels out one row at a time.
    def setImage(self, height = None, yOffset = 0, shouldAbort = False):
        if shouldAbort:
            self.connobj.connection.abort()
            self.connobj.connection.settrigger(True)
            self.connobj.connection.setExposureTime(self.lastExposureTime)
        newHeight, newWidth = self.connobj.connection.setImage(
            0, yOffset, None, height)
        # There are some "extra" pixels on the sides that we want to skip,
        # because they may be partially covered by an aluminized strip.
        left = right = (newWidth - 506) / 2
        top = bottom = (newHeight - 506) / 2
        if height is not None:
            top = bottom = (newHeight - height) / 2
        self.imageSize = self.connobj.connection.setskipLRTB(
                left, right, top, bottom)[::-1]
        # Some of these pixels will be used to clamp the baseline of the
        # output image. These pixels are not actually exposed to any light
        # (hence "dark") but their output varies with the baseline anyway.
        self.connobj.connection.setdarkLRTB(2, 0, 0, 0)
        self.connobj.connection.exposeTillAbort(0)
        self.flushCache()

    
class CameraManager(camera.CameraManager):
    _CAMERA_CLASS = AndorEMCCDCameraDevice
    _SUPPORTED_CAMERAS = SUPPORTED_CAMERAS

    def getUILabel(self):
        return 'Ixon Cameras'
