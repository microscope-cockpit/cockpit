import device
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

## Describes the settings used to connect a given camera. 
CameraSettings = collections.namedtuple('CameraSettings',
        ['is16Bit', 'isConventional', 'speed'])

CLASS_NAME = 'CameraDevice'

class CameraDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Maps camera names to Connection instances.
        self.nameToConnection = {}
        ## Maps camera names to the images they generate.
        self.nameToImageSize = {}
        ## Maps camera names to cached copies of their exposure times.
        self.nameToExposureTime = {}
        ## Maps camera names to cached copies of their time between exposures.
        self.nameToTimeBetweenExposures = {}
        ## Maps camera names to if they are iXon+ cameras.
        self.nameToIsIxonPlus = {}
        ## Last-set exposure time we used.
        self.lastExposureTime = 100
        ## Last-set "global" EM gain we used.
        self.lastEMGain = 0
        ## Maps camera names to EM gains used for those cameras.
        self.nameToGain = {}
        ## Last-set camera settings we used.
        self.lastSettings = None
        ## Maps toggle buttons to CameraSettings instances.
        self.buttonToSettings = {}
        ## Button for the EM gain setting.
        self.gainButton = None
        ## Panel containing the above buttons.
        self.panel = None
        ## List of available image readout sizes.
        self.imageSizes = ['Full', '512x256', '512x128']
        

    def getHandlers(self):
        result = []
#IMD 20130212 changed to reflect the presence of 1 camera on OMXT-Oxford
        for name, ipAddress, isIxonPlus in [
               # ('West', '172.16.0.20', True)]:
                #,
                ('East', '172.16.0.1', False)]:
                #('Northwest', '172.16.0.22', False),
                #('Northeast', '172.16.0.23', True)]:
            result.append(handlers.camera.CameraHandler(
                "%s" % name, "Evolve camera", 
                {'setEnabled': self.enableCamera, 
                    'getImageSize': self.getImageSize, 
                    'getTimeBetweenExposures': self.getTimeBetweenExposures, 
                    'prepareForExperiment': self.prepareForExperiment,
                    'getExposureTime': self.getExposureTime,
                    'setExposureTime': self.setExposureTime,
                    'getImageSizes': self.getImageSizes,
                    'setImageSize': self.setImageSize},
                True))
            self.nameToConnection[name] = util.connection.Connection(
                    'pyroCam', ipAddress, 7775)
            self.nameToIsIxonPlus[name] = isIxonPlus
        return result


    ## Generate a grid of buttons for setting the camera mode and
    # EM gain.
    def makeUI(self, parent):
        # Create a panel because we want to isolate the EM Gain's
        # menu events from our parent.
        self.panel = wx.Panel(parent)
        self.panel.SetBackgroundColour((170, 170, 170))
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self.panel, -1, "Evolve EMCCD controls:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.gainButton = gui.toggleButton.ToggleButton(
                label = "EM Gain\n%d" % self.lastEMGain,
                parent = self.panel, size = (168, 100))
        self.gainButton.Bind(wx.EVT_LEFT_DOWN, self.onGainButton)
        rowSizer.Add(self.gainButton)
        
        modeSizer = wx.GridSizer(2, 4)
        for label, is16Bit, isConventional, speed in [
                ('EM\n10MHz', True, False, 0),
                ('EM\n20MHz', True, False, 1),
                ('Conv\n10MHz', True, True,1 )]:
            button = gui.toggleButton.ToggleButton(
                label = label, parent = self.panel, size = (84, 50)
            )
            button.Bind(wx.EVT_LEFT_DOWN,
                    lambda event, button = button: self.onModeButton(button))
            modeSizer.Add(button)
            settings = CameraSettings(is16Bit, isConventional, speed)
            self.buttonToSettings[button] = settings
            if len(self.buttonToSettings) == 3:
                # 7th button  starts out activated (ie 3Mhz Conv).
                self.onModeButton(button)
        rowSizer.Add(modeSizer)
        sizer.Add(rowSizer)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    ## Handle the user clicking on the EM gain button. Pop
    # up a menu of possible gain values, including the option
    # to set them on a per-camera basis.
    def onGainButton(self, event = None):
        menu = wx.Menu()
        menuId = 1
        for value in range(0, 255, 10):
            menu.Append(menuId, str(value))
            wx.EVT_MENU(self.panel, menuId, lambda event, value = value: self.setGain(value))
            menuId += 1
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    ## Set the gain for a camera, or for all cameras if none is
    # specified.
    def setGain(self, value, camera = None):
        iterator = [camera]
        print "in setgain"
        if camera is None:
            iterator = self.nameToConnection.keys()
        for cameraName in iterator:
            if self.nameToConnection[cameraName].getIsConnected():
                connection = self.nameToConnection[cameraName].connection
                self.nameToGain[cameraName] = value
                # This will make it pick up the new gain.
                self.resetCamera(cameraName)
        # Update the button to show each camera's gain.
        label = 'EM Gain:\n'
        for name, gain in sorted(self.nameToGain.items()):
            label += '%s: %s\n' % (name, gain)
            print label
        self.gainButton.SetLabel(label)


    ## Handle the user clicking on one of the camera mode buttons.
    def onModeButton(self, button):
        settings = self.buttonToSettings[button]
        print "mode button settings", settings
        self.lastSettings = settings
        for altButton in self.buttonToSettings.keys():
            altButton.setActive(button is altButton)
        # No EM gain in conventional mode.
        self.gainButton.Enable(not settings.isConventional)
        for name, conn in self.nameToConnection.iteritems():
            if conn.getIsConnected():
                # This will apply self.lastSettings.
                self.resetCamera(name)
            self.flushCache(name)


    ## Flush any relevant caches we have for the specified camera.
    def flushCache(self, name):
        if name in self.nameToTimeBetweenExposures:
            del self.nameToTimeBetweenExposures[name]


    ## Abort all cameras.
    def abort(self):
        for conn in self.nameToConnection.values():
            if conn.getIsConnected():
                conn.connection.abort()
            

    ## Receive data from a camera.
    def receiveData(self, name, action, *args):
        if action == 'new image':
            (image,) = args
            events.publish('new image %s' % name, image)


    ## Handle a camera connecting or disconnecting.
    @util.threads.callInNewThread
    def enableCamera(self, name, isOn):
        if isOn:
            self.nameToConnection[name].connect(lambda *args: self.receiveData(name, *args))
            connection = self.nameToConnection[name].connection
            # The start() function can take a long time.
            connection._pyroTimeout = 40
            try:
                connection.abort()
            except Exception, e:
                # Camera can't abort, probably because it hasn't been
                # initialized yet; no big deal.
                pass
            thread = gui.guiUtils.WaitMessageDialog(
                    "Connecting to %s" % name, "Please wait", .5)
            thread.start()
            print "start ",name
            try:
                connection.init()
                #IMD start on evolve only tajkes one argument
                connection.start()
                #self.nameToIsIxonPlus[name])
            except Exception:
                # Something's wrong with the camera; try re-initializing and
                # then reconnecting.
                try:
                    connection.init()
                    #IMD start on evolve only tajkes one argument
                    connection.start()
                    #self.nameToIsIxonPlus[name])
                except Exception, e:
                    thread.shouldStop = True
                    raise e
            thread.shouldStop = True
            connection._pyroTimeout = 3
            connection.settemp(-71)
            self.resetCamera(name)
        else:
            self.nameToConnection[name].connection.abort()
            self.nameToConnection[name].connection.quit()
            self.nameToConnection[name].disconnect()


    ## Get the amount of time that must pass after stopping one exposure
    # before another can be started, in milliseconds.
    def getTimeBetweenExposures(self, name, isExact = False):
        result = None
        if name in self.nameToTimeBetweenExposures:
            # Have a cached copy.
            result = self.nameToTimeBetweenExposures[name]
        else:
            # Go to our connection to get the value.
            connection = self.nameToConnection[name].connection
            # Exposure time is folded into the readout time, so subtract
            # it off.
#IMD 20130815 evolve timings are found digfferently.
#            result = connection.getTimesExpAccKin()[2] - connection.getexp()
#IMD 20130913 pvcam get cycle time is broken.
# fudge it!
#           result = connection.getCycleTime() - connection.getexp()
            result = 70
            self.nameToTimeBetweenExposures[name] = result
        if isExact:
            result = decimal.Decimal(result)
        return result


    ## Set the exposure time for this camera, in milliseconds.
    def setExposureTime(self, name, time):
#        print "exposure time",name,time
        if (name in self.nameToExposureTime and
                abs(self.nameToExposureTime[name] - time) < .1):
            # Don't bother; we're already there.
            return
        connection = self.nameToConnection[name].connection
        connection.abort()
        connection.setExposureTime(time)
        connection.settrigger(True)
        connection.exposeTillAbort(False)
        self.nameToExposureTime[name] = time
        self.flushCache(name)


    ## Return the exposure time for this camera, in milliseconds.
    def getExposureTime(self, name, isExact = False):
        result = self.nameToConnection[name].connection.getexp()
        if isExact:
            result = decimal.Decimal(result)
        return result


    ## Get a list of strings describing the available image sizes.
    def getImageSizes(self, name):
        return self.imageSizes


    ## Set the image size for the specified camera.
    # \param size One of the strings from self.imageSizes
    def setImageSize(self, name, size):
        height = None
        yOffset = 0
        if 'x' in size:
            width, height = map(int, size.split('x'))
            yOffset = 256 - height / 2
        self.setImage(name, height, yOffset, shouldAbort = True)
        

    ## Get the size of the image this camera generates.
    def getImageSize(self, name):
        return self.nameToImageSize[name]


    ## Get the camera ready for an experiment. Ensure it's in frame-transfer
    # mode, with an exposure time of 0 (so that getFramerate returns the 
    # minimum time between exposures.
    def prepareForExperiment(self, name, experiment):
        connection = self.nameToConnection[name].connection
        connection.abort()
        connection.setExposureTime(0)
        connection.settrigger(True)
        # Since we'll be in frame-transfer mode, we'll be accumulating light
        # until the next external trigger. This causes a lot of background in
        # the first image. So we'll trigger the first image immediately before
        # starting the experiment (or as close-to as possible) and discard it.
#        connection.skipNextNimages(1)
        connection.exposeTillAbort(1)
        self.flushCache(name)


    ## Reset the camera to a baseline state.
    def resetCamera(self, name):
        connection = self.nameToConnection[name].connection
        connection.abort()
        connection.cammode(self.lastSettings.is16Bit,
                self.lastSettings.isConventional,
                self.lastSettings.speed,
                self.nameToGain.get(name, self.lastEMGain), None)
        connection.settrigger(True)
        connection.setshutter(1)
        connection.setExposureTime(self.lastExposureTime)
        self.setImage(name)


    ## Set the image shape for the camera. We only vary the height of the
    # image, not the width, since we read pixels out one row at a time.
    def setImage(self, name, height = None, yOffset = 0, shouldAbort = False):
        connection = self.nameToConnection[name].connection
        if shouldAbort:
            connection.abort()
            connection.settrigger(True)
            connection.setExposureTime(self.lastExposureTime)
        newHeight, newWidth = connection.setImage(0, yOffset, None, height)
        self.nameToImageSize[name] = (newWidth, newHeight)
        # There are some "extra" pixels on the sides that we want to skip.
        left = right = (newWidth - 512) / 2
        top = bottom = 0
        if height is not None:
            top = bottom = (newHeight - height) / 2
#IMD 20130815
#Evolves dont allow direct access to extra pixels
#        connection.setskipLRTB(left, right, top, bottom)
        connection.exposeTillAbort(1)
        self.flushCache(name)

    
