import decimal
import os
import sys
import threading
import time
import wx

import depot
import device
import events
import gui.dialogs.getNumberDialog
import gui.toggleButton
import handlers.stagePositioner
import util.threads

# HACK: we'll want access to this module later, but can't import it now (as 
# Python's path isn't set properly yet),
# so just add it to the global namespace for the moment. It will get replaced
# in MMDevice.initialize().
MMCorePy = None

## Path to MicroManager.
MM_PATH = os.path.join('C:', os.path.sep, 'Program Files', 'Micro-Manager-1.4.15')
## Relative path to the configuration file for MicroManager.
CONFIG_PATH = os.path.join('devices', 'resources', 'microManagerConfig.cfg')

CLASS_NAME = "MMDevice"



## This class wraps around MicroManager and provides access to its devices.
class MMDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Initialize this first, before practically everything else.
        self.priority = 1
        ## MicroManager CMMCore object.
        self.core = None
        ## Maps Handler names to those Handlers.
        self.nameToHandler = None
        ## Set of active CameraHandler names.
        self.activeCams = set()
        ## Set of sub-devices.
        self.subDevices = set()
        ## Camera sub-devices
        self.camDevices = set()
        events.subscribe('light source enable', self.onLightEnable)


    ## Initialize MicroManager; create the core object and load configuration.
    def initialize(self):
        # Adjust the system path so it can find MMCorePy.
        sys.path.append(MM_PATH)
        # Adjust the PATH environment variable so it can find MicroManager
        # DLLs.
        os.environ['PATH'] = MM_PATH + ';' + os.environ['PATH']

        # Allow the MMCorePy object to be accessed from elsewhere in this
        # module.
        global MMCorePy
        import MMCorePy
        self.core = MMCorePy.CMMCore()
        self.core.loadSystemConfiguration(CONFIG_PATH)
        events.subscribe('program exit', self.onExit)

        # Load cameras.
        for cameraName in self.core.getLoadedDevicesOfType(MMCorePy.CameraDevice):
            camera = MMCamera(self.core, cameraName, self.setCamEnabled)
            self.subDevices.add(camera)
            self.camDevices.add(camera)
        # Load the stage(s)
        for stageName in self.core.getLoadedDevicesOfType(MMCorePy.XYStageDevice):
            stage = MMXYStage(self.core, stageName)
            self.subDevices.add(stage)
        # Load shutter selector.
        self.subDevices.add(MMShutter(self.core, 'Core'))
        
        # \todo Assuming all StageDevices that have a Position property
        # are Z stage positioners. This seems unwise, but there's no explicit
        # Z positioner device as far as I can tell.
        for stageName in self.core.getLoadedDevicesOfType(MMCorePy.StageDevice):
            if 'Position' in self.core.getDevicePropertyNames(stageName):
                stage = MMZStage(self.core, stageName)
                self.subDevices.add(stage)
        # Load the autofocus device, if any.
        if self.core.getAutoFocusDevice():
            autofocus = MMAutoFocus(self.core, self.core.getAutoFocusDevice())
            self.subDevices.add(autofocus)
        

    ## Examine our available devices and generate handlers for them.
    def getHandlers(self):
        result = []
        for device in self.subDevices:
            result.extend(device.getHandlers())
        self.nameToHandler = dict([(handler.name, handler) for handler in result])
        return result


    ## Generate any UI elements.
    def makeUI(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        toggle = gui.toggleButton.ToggleButton(label = "Property browser",
                parent = panel, size = (120, 50))
        toggle.Bind(wx.EVT_LEFT_DOWN, self.makeBrowser)
        toggle.Bind(wx.EVT_RIGHT_DOWN, self.makeBrowser)
        sizer.Add(toggle)
        for device in sorted(self.subDevices, key = lambda d: d.name):
            result = device.makeUI(panel)
            if result is not None:
                sizer.Add(result)
        panel.SetSizerAndFit(sizer)
        return panel


    ## Make our own version of the Property Browser window.
    def makeBrowser(self, event = None):
        window = wx.Frame(parent = None,
                title = "MicroManager property browser")
        panel = wx.ScrolledWindow(window)
        sizer = wx.BoxSizer(wx.VERTICAL)
        bigFont = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        for device in sorted(self.core.getLoadedDevices(),
                key = lambda d: d.lower()):
            header = wx.StaticText(panel, -1, device)
            header.SetBackgroundColour((255, 255, 255))
            header.SetFont(bigFont)
            sizer.Add(header, 1, wx.EXPAND)
            for i, propertyName in enumerate(self.getPropertiesFor(device)):
                row = wx.Panel(panel)
                color = [(225, 225, 225), (200, 200, 200)][i % 2]
                row.SetBackgroundColour(color)
                rowSizer = wx.BoxSizer(wx.HORIZONTAL)
                name = wx.StaticText(row, -1, propertyName)
                rowSizer.Add(name, 1, wx.EXPAND | wx.HORIZONTAL)

                allowedVals = self.core.getAllowedPropertyValues(device, propertyName)
                control = None
                curVal = self.core.getProperty(device, propertyName)
                if self.core.isPropertyReadOnly(device, propertyName):
                    # Use a static text, since the user can't modify it anyway.
                    control = wx.StaticText(row, -1, str(curVal))
                elif len(allowedVals):
                    # Use a dropdown menu.
                    control = wx.Choice(row, -1, choices = allowedVals)
                    control.Bind(wx.EVT_CHOICE, self.makeChoice(device, propertyName, control))
                    if curVal in allowedVals:
                        control.SetSelection(allowedVals.index(curVal))
                    else:
                        print "What? Current value [%s] for device %s property %s is not allowed?" % (curVal, device, propertyName)
                else:
                    # Use a text control.
                    control = wx.TextCtrl(row, -1, style = wx.TE_PROCESS_ENTER)
                    control.SetValue(curVal)
                    control.Bind(wx.EVT_TEXT_ENTER, self.makeTextEntry(device, propertyName, control))
                rowSizer.Add(control, 1, wx.EXPAND | wx.HORIZONTAL)
                row.SetSizerAndFit(rowSizer)
                sizer.Add(row, 1, wx.EXPAND | wx.HORIZONTAL)
        panel.SetSizer(sizer)
        panel.FitInside()
        panel.SetScrollRate(5, 20)
        window.SetSize((640, 480))
        window.Show()


    ## Make a function that sets the given property to the wx.Choice's
    # current selection. This just makes the above function a bit cleaner,
    # since using lambdas in loops in Python doesn't work well.
    def makeChoice(self, device, propertyName, control):
        # Must cast away from Unicode strings for MicroManager to be happy.
        return lambda event: self.core.setProperty(
                device, propertyName, str(control.GetStringSelection()))


    ## As above, but for wx.TextCtrl instead.
    def makeTextEntry(self, device, propertyName, control):
        return lambda event: self.core.setProperty(
                device, propertyName, str(control.GetValue()))


    ## Passthrough to our sub-devices.
    def makeInitialPublications(self):
        for device in self.subDevices:
            device.makeInitialPublications()


    ## Enable/disable a camera.
    def setCamEnabled(self, name, isEnabled):
        if isEnabled:
            self.activeCams.add(name)
        elif name in self.activeCams:
            self.activeCams.remove(name)


    ## A light source was enabled or disabled. Update our camera exposure
    # time. We do this here instead of in takeImage because takeImage can
    # be called during experiments with very specific exposure times which
    # don't necessarily map to the currently-active lights.
    def onLightEnable(self, lightSource, isOn):
        # Find the light source with the longest exposure time; that
        # determines our camera's exposure time.
        lights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        exposureTime = 0
        for light in lights:
            if light.getIsEnabled():
                exposureTime = max(exposureTime, light.getExposureTime())
        if self.core.getExposure() != exposureTime:
            self.core.setExposure(exposureTime)


    ## Take an image with the current settings.
    def takeImage(self):
        if self.activeCams:
            lights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
            lights = filter (lambda l: l.getIsEnabled(), lights)
            # HACK: stick a [0] on there in case there are no active lights.
            maxTime = max([l.getExposureTime() for l in lights] + [0])
            self.core.setExposure(maxTime)
            start = time.time()
            self.core.snapImage()
            timestamp = time.time()
            image = self.core.getImage()
            for subCamera in self.camDevices:
                events.publish('new image %s' % subCamera.name, image, timestamp)


    ## Access the core object.
    def getCore(self):
        return self.core
            

    ## Program is exiting; shut down devices.
    def onExit(self, *args):
        self.core.unloadAllDevices()


    ## Debugging function: generate a list of properties for the named
    # MicroManager device.
    def getPropertiesFor(self, name):
        return self.core.getDevicePropertyNames(name)


    ## Debugging function: print the arguments for all calls to setProperty.
    def logSetProperty(self):
        self.core._setProperty = self.core.setProperty
        def setP(*args):
            print "setProperty called with",args
            self.core._setProperty(*args)
        self.core.setProperty = setP



## Sub-device base class for handling specific aspects of MicroManager devices.
class SubDevice:
    ## \param core The MicroManager core object.
    # \param name Name of the camera we are controlling.
    def __init__(self, core, name):
        self.core = core
        self.name = name

    
    ## Publish any information needed at the start of the program.
    def makeInitialPublications(self):
        pass


    ## Generate DeviceHandlers.
    def getHandlers(self):
        return []


    ## Make any UI elements we need.
    def makeUI(self, parent):
        return None

        

## Subclass for handling cameras. Note that we don't generate any CameraHandlers
# here; instead, those are created by whatever is responsible for emission
# filters.
class MMCamera(SubDevice):
    ## \param enableCallback Function to call when the camera is enabled/disabled
    def __init__(self, core, name, enableCallback):
        SubDevice.__init__(self, core, name)
        self.enableCallback = enableCallback


    ## Return the minimum time that must pass between each exposure of the
    # camera. 
    def getTimeBetweenExposures(self, name, isExact = False):
        result = float(self.core.getProperty(self.name, 'ActualInterval-ms'))
        if isExact:
            return decimal.Decimal(result)
        return result


    ## Prepare the camera for an experiment.
    def prepareForExperiment(self, name, *args):
        pass


    ## Get the camera's current exposure time.
    def getExposureTime(self, name, isExact = False):
        result = float(self.core.getProperty(name, 'Exposure'))
        if isExact:
            return decimal.Decimal(result)
        return result


    ## Set the camera's current exposure time.
    def setExposureTime(self, name, val):
        # Ensure that the value used is floating point, and not, say,
        # a decimal.Decimal object.
        self.core.setProperty(name, 'Exposure', float(val))


    ## Return the readout image size for the given camera.
    def getImageSize(self, name):
        width = int(self.core.getProperty(name, 'X-dimension'))
        height = int(self.core.getProperty(name, 'Y-dimension'))
        return (width, height)       


    ## Return a list of all available image sizes for the given camera.
    # \todo For now, not allowing any adjustments.
    def getImageSizes(self, name):
        return [self.getImageSize(name)]


    ## Set the image size for the given camera to the provided value.
    # \todo For now, not allowing any adjustments.
    def setImageSize(self, name, val):
        pass
    


## Subclass for handling stage positioners.
class MMXYStage(SubDevice):
    def __init__(self, core, name):
        SubDevice.__init__(self, core, name)
        ## [X position, Y position] list, caching values.
        self.curPosition = [core.getXPosition(name), core.getYPosition(name)]
        ## [X position, Y position] current movement target.
        self.curTarget = [None, None]
        ## Thread that's sending position updates.
        self.updateThread = None
        ## Cached position prior to the start of the experiment.
        self.preExperimentPosition = None

        self.pollStagePosition()

        events.subscribe('prepare for experiment', self.onPrepareForExperiment)


    ## Generate a handler for each axis of motion.
    def getHandlers(self):
        result = []
        # X axis is 0, Y axis is 1.
        for axis in range(2):
            # Min/max positions are arbitrary since we have no way to get
            # the actual range of motion.
            result.append(handlers.stagePositioner.PositionerHandler(
                    "%d %s" % (axis, self.name), "%d stage motion" % axis,
                    True,
                    {
                        'moveAbsolute': self.moveAbsolute,
                        'moveRelative': self.moveRelative,
                        'getPosition': self.getPosition,
                        'setSafety': self.setSafety,
                        'getMovementTime': self.getMovementTime,
                        'cleanupAfterExperiment': self.cleanupAfterExperiment,
                    },
                    axis, [.1, .2, .5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000],
                    3, [-100000, 100000], [-100000, 100000]
            ))
        return result


    ## Let everyone know where the stage is.
    def makeInitialPublications(self):
        self.sendPositionUpdates()


    ## Move the given axis to the specified position. Movement functions are
    # a bit tricky, as we have to tell the stage where to go in both X and Y
    # whenever we want to move either axis. So we have to track our targets
    # in both axes, in case we want to move diagonally (as such commands come
    # as two separate calls to moveAbsolute).
    def moveAbsolute(self, axis, val):
        if abs(val - self.curPosition[axis]) < .01:
            # Ignore no-ops.
            return
        self.curTarget[axis] = val
        self.core.setXYPosition(self.name, *self.curTarget)


    ## Move the given axis by the specified delta.
    def moveRelative(self, axis, delta):
        self.moveAbsolute(axis, self.curPosition[axis] + delta)


    ## Get the position of the noted axis.
    def getPosition(self, axis):
        return self.curPosition[axis]


    ## Adjust the software safeties. A no-op since we have none.
    def setSafety(self, *args):
        pass


    ## Update the rest of the Cockpit with the current stage position, until
    # it stops moving.
    @util.threads.callInNewThread
    def sendPositionUpdates(self):
        while True:
            prevX, prevY = self.curPosition
            x = self.core.getXPosition(self.name)
            y = self.core.getYPosition(self.name)
            self.curPosition = [x, y]
            # Update our "target" position, so that future movement commands
            # can blindly use it for no-op moves.
            self.curTarget = list(self.curPosition)
            delta = abs(x - prevX) + abs(y - prevY)
            if delta < .1:
                # No movement of note; done moving.
                for axis, val in enumerate([x, y]):
                    events.publish('stage mover', '%d %s' % (axis, self.name),
                            axis, val)
                    events.publish('stage stopped', '%d %s' % (axis, self.name))
                return
            for axis, val in enumerate([x, y]):
                events.publish('stage mover', '%d %s' % (axis, self.name),
                        axis, val)
            time.sleep(.1)


    ## Get the amount of time it takes for us to move from the given start
    # position to the given stop position, and the amount of stabilization
    # time afterwards. I've no idea how to extract this information, so these
    # values are made up; assuming 1mm/sec speed and 100ms stabilization time.
    def getMovementTime(self, axis, start, end):
        return (decimal.Decimal(abs(start - end) * .001), decimal.Decimal(100))


    ## An experiment is about to start; record our position.
    def onPrepareForExperiment(self, *args):
        self.preExperimentPosition = list(self.curPosition)


    ## An experiment has finished; clean things up.
    def cleanupAfterExperiment(self, *args):
        for axis in xrange(2):
            self.moveAbsolute(axis, self.preExperimentPosition[axis])


    ## Periodically poll the stage to see if it has moved.
    @util.threads.callInNewThread
    def pollStagePosition(self):
        while True:
            x = self.core.getXPosition(self.name)
            y = self.core.getYPosition(self.name)
            if x != self.curPosition[0] or y != self.curPosition[1]:
                # Only create a new updater thread if we don't already have one going.
                if self.updateThread is None or not self.updateThread.isAlive():
                    self.updateThread = threading.Thread(target = self.sendPositionUpdates)
                    self.updateThread.start()
            time.sleep(.1)




## Represents a Z stage motion device.
class MMZStage(SubDevice):
    def __init__(self, core, name):
        SubDevice.__init__(self, core, name)
        self.curPosition = None
        ## Cached position prior to the start of the experiment.
        self.preExperimentPosition = None

        self.pollStagePosition()

        events.subscribe('prepare for experiment', self.onPrepareForExperiment)

        
    def getHandlers(self):
        # 2 is the Z axis.
        # Note that our movement limits are entirely fabricated.
        return [handlers.stagePositioner.PositionerHandler(
                "%d %s" % (2, self.name), "%d stage motion" % 2,
                True,
                {
                    'moveAbsolute': self.moveAbsolute,
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition,
                    'setSafety': self.setSafety,
                    'getMovementTime': self.getMovementTime,
                    'cleanupAfterExperiment': self.cleanupAfterExperiment
                },
                2, [.1, .2, .5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000],
                3, [-5000, 5000], [-5000, 5000]
        )]


    def makeInitialPublications(self):
        self.curPosition = self.getPosition()


    ## Move to a specific location.
    def moveAbsolute(self, axis, val):
        self.core.setProperty(self.name, 'Position', val)


    ## Move by a specific offset.
    def moveRelative(self, axis, delta):
        self.moveAbsolute(axis, self.getPosition() + delta)


    ## Get the current position.
    def getPosition(self, *args):
        return float(self.core.getProperty(self.name, 'Position'))


    ## Set software motion limits. Disabled for now since we have no idea what
    # our range of motion is.
    def setSafety(self, *args):
        pass


    ## Update the rest of the Cockpit with the current stage position, until
    # it stops moving. Largely copied from MMXYStage.
    @util.threads.callInNewThread
    def sendPositionUpdates(self):
        while True:
            prevPos = self.curPosition
            self.curPosition = self.getPosition()
            if prevPos is None:
                continue
            delta = abs(self.curPosition - prevPos)
            if delta < .1:
                # No movement of note; done moving.
                events.publish('stage mover', '%d %s' % (2, self.name), 2,
                        self.curPosition)
                events.publish('stage stopped', '%d %s' % (2, self.name))
                return
            events.publish('stage mover', '%d %s' % (2, self.name), 2,
                    self.curPosition)
            time.sleep(.1)


    ## Get the amount of time it takes for us to move from the given start
    # position to the given stop position, and the amount of stabilization
    # time afterwards. I've no idea how to extract this information, so these
    # values are made up; assuming 1mm/sec speed and 100ms stabilization time.
    def getMovementTime(self, axis, start, end):
        return (decimal.Decimal(abs(start - end) * .001), decimal.Decimal(100))


    ## An experiment is about to start; record our position.
    def onPrepareForExperiment(self, *args):
        self.preExperimentPosition = self.curPosition


    ## An experiment has finished; clean things up.
    def cleanupAfterExperiment(self, *args):
        self.moveAbsolute(2, self.preExperimentPosition)


    ## Periodically poll the stage to see if it has moved.
    @util.threads.callInNewThread
    def pollStagePosition(self):
        while True:
            pos = self.getPosition()
            if pos != self.curPosition:
                self.sendPositionUpdates()
            time.sleep(.1)



## Class for handling autofocus/perfect focus devices.
class MMAutoFocus(SubDevice):
    ## Provide a button for turning autofocus on and off.
    def makeUI(self, parent):
        self.button = gui.toggleButton.ToggleButton(parent = parent,
                label = "Auto-focus", size = (168, 50))
        self.button.Bind(wx.EVT_LEFT_DOWN, self.toggle)
        self.button.setActive(self.core.getProperty(self.name, 'State') == 'On')
        return self.button


    ## Toggle autofocus on/off.
    def toggle(self, event = None):
        if self.core.getProperty(self.name, 'State') == 'Off':
            self.core.setProperty(self.name, 'State', 'On')
        else:
            self.core.setProperty(self.name, 'State', 'Off')
        # Check if we succeeded.
        if self.core.getProperty(self.name, 'State') == 'On':
            self.button.activate()
        else:
            self.button.deactivate()



## Class for handling shutter selection.
class MMShutter(SubDevice):
    def __init__(self, *args):
        SubDevice.__init__(self, *args)
        ## wx.Choice indicating the currently-selected shutter.
        self.menu = None
        events.subscribe('MM shutter change', self.onShutterChange)

        
    def makeUI(self, parent):
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, -1, "Shutter:"))
        shutters = self.core.getAllowedPropertyValues(self.name, 'Shutter')
        self.menu = wx.Choice(panel, -1, choices = shutters)
        def setShutter(event):
            # Cast away from Unicode string.
            selection = str(self.menu.GetStringSelection())
            self.core.setProperty(self.name, 'Shutter', selection)
        self.menu.Bind(wx.EVT_CHOICE, setShutter)
        sizer.Add(self.menu)
        panel.SetSizerAndFit(sizer)
        return panel


    def onShutterChange(self, newShutter):
        self.menu.SetStringSelection(newShutter)
        
