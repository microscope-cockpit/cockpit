## This Device specifies a "drawer" of optics and filters that determines
# what cameras see what lights.
# It also creates a set of "virtual cameras" that are associated with 
# each emission filter, and handles translating images received from the 
# actual camera to the virtual cameras. 

import depot
import device
import events
import gui.guiUtils
import gui.toggleButton
import handlers.camera
import handlers.drawer
import handlers.executor
import handlers.imager
import microManager
import util.userConfig

import decimal
import time
import wx

## Maps dye names to colors to use for those dyes.
DYE_TO_COLOR = {
        'Cy5': (0, 255, 255),
        'DAPI': (184, 0, 184),
        'DIC': (128, 128, 128),
        'FITC': (80,255,150),
        'GFP': (0, 255, 0),
        'mCherry': (255, 0, 0),
        'RFP': (255, 0, 0),
        'TRITC': (255, 0, 0),
        'Rhod': (255,80,20),
        'YFP': (255, 255, 0),
        'YFP HYQ': (255, 255, 0),
}

CLASS_NAME = 'EmissionFilterDevice'



class EmissionFilterDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## MicroManager core object.
        self.core = None
        ## We must be initialized after the MicroManager device.
        self.priority = 1000
        ## List of valid filter position labels. The index of a label
        # corresponds to its position in the wheel. Why is there a
        # duplicate? I don't know. Because of how we set the filter position
        # by name, it's inaccessible, but removing it would throw off all our
        # indices. If it is to be accessible, it must have a subtly different
        # (here have appended 2) or else it becomes inaccessible.
        self.options = ['Empty', 'ANALYZER', 'Empty2', 'YFP HYQ',
                'DAPI', 'FITC', 'FITC2', 'TRITC', 'Full', 'BFP']
        ## Maps option names (above) to their corresponding wavelengths,
        # where applicable.
        self.optionToWavelength = {
            'Empty': 0,
            'ANALYZER': 0,
            'YFP HYQ': 530,
            'DAPI': 455,
            'FITC': 519,
            'TRITC': 572,
            'Full': 0,
            'BFP': 440,
        }
        ## Maps camera names to the corresponding filter option.
        self.nameToFilter = {}
        ## Maps LightSource instances to current camera gain values for those
        # lights.
        self.lightToGain = {}
        ## Maps LightSource instances to corresponding emission filter to use
        # when imaging with that light.
        self.lightToFilter = {}
        ## Maps LightSource instances to ToggleButtons for their associated
        # filters.
        self.lightToFilterButton = {}
        ## Maps LightSource instances to ToggleButtons for their associated
        # gains.
        self.lightToGainButton = {}
        ## Label of the currently-set filter.
        self.curFilter = None
        ## Menu for selecting the emission filter.
        self.menu = None
        ## DrawerHandler representing our filter set.
        self.drawerHandler = None
        ## MMCamera instance (see the microManager module).
        self.coreCam = None
        ## Set of currently active simulated cameras.
        self.curActiveViews = set()

        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)


    def initialize(self):
        mmDevice = depot.getDevice(microManager)
        self.core = mmDevice.getCore()
        self.coreCam = list(mmDevice.camDevices)[0]
        events.subscribe('new image %s' % self.coreCam.name, self.onImage)
        events.subscribe('user login', self.onLogin)
        events.subscribe('camera enable', self.onCameraEnable)
        events.subscribe('create light controls', self.onLightControl)


    ## In addition to the DrawerHandler, we make one CameraHandler per
    # available emission filter, and an Executor for changing the filter
    # mid-experiment.
    def getHandlers(self):
        self.drawerHandler = handlers.drawer.DrawerHandler(
                "emission filter", "miscellaneous",
                callbacks =
                {'getWavelengthForCamera': self.getWavelengthForCamera,
                 'getDyeForCamera': self.getDyeForCamera,
                 'getColorForCamera': self.getColorForCamera}
                )
        result = [self.drawerHandler]
        # Add an executor for taking images.
        result.append(handlers.imager.ImagerHandler(
                'Emission filter imager', 'miscellaneous',
                {
                    'takeImage': self.takeImage
                }
        ))


        # Generate synthetic cameras, one per filter.
        # Cast to set so we don't get duplicates.
        for filterName in set(self.options):
            camName = "%s (%s)" % (self.coreCam.name, filterName)
            result.append(handlers.camera.CameraHandler(
                camName, "Cameras",
                {
                    'setEnabled': self.wrap(self.coreCam.enableCallback),
                    'getTimeBetweenExposures': self.wrap(self.coreCam.getTimeBetweenExposures),
                    'prepareForExperiment': self.wrap(self.coreCam.prepareForExperiment),
                    'getExposureTime': self.wrap(self.coreCam.getExposureTime),
                    'setExposureTime': self.wrap(self.coreCam.setExposureTime),
                    'getMinExposureTime': lambda *args: 10,
                    'getImageSizes': self.wrap(self.coreCam.getImageSizes),
                    'getImageSize': self.wrap(self.coreCam.getImageSize),
                    'setImageSize': self.wrap(self.coreCam.setImageSize),
                }, handlers.camera.TRIGGER_DURATION))
            self.nameToFilter[camName] = filterName
        return result


    ## Wrap a function provided by self.coreCam so that the name matches.
    def wrap(self, func):
        return lambda name, *args: func(self.coreCam.name, *args)


    ## User logged in; restore their previous emission filter.
    def onLogin(self, *args):
        prevPos = util.userConfig.getValue('EmissionFilter', default = 'Empty')
        self.setPosition(prevPos)


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        result = dict()
        result['curFilter'] = self.curFilter
        for light, gain in self.lightToGain.iteritems():
            subResult = dict()
            subResult['gain'] = gain
            if light in self.lightToFilter:
                subResult['filter'] = self.lightToFilter[light]
            result[light.name] = subResult
        settings['emissionFilterSettings'] = result


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        if 'emissionFilterSettings' in settings:
            for key, val in settings['emissionFilterSettings'].iteritems():
                if key == 'curFilter':
                    self.setPosition(val)
                else:
                    # Must be a setting for a light source. Get the
                    # light source handler.
                    light = depot.getHandlerWithName(key)
                    self.lightToGain[light] = val['gain']
                    self.lightToGainButton[light].SetLabel('Gain: %s' % val['gain'])
                    if 'filter' in val:
                        self.lightToFilter[light] = val['filter']
                        self.lightToFilterButton[light].SetLabel('Emission: %s' % val['filter'])


    ## Camera enabled or disabled. If we have exactly 1 camera, set the
    # corresponding emission filter.
    def onCameraEnable(self, camera, isEnabled):
        if not isEnabled and camera in self.curActiveViews:
            self.curActiveViews.remove(camera)
        elif isEnabled:
            self.curActiveViews.add(camera)
        if len(self.curActiveViews) == 1:
            camera = list(self.curActiveViews)[0]
            self.setPosition(self.nameToFilter[camera.name])


    ## Creating the lightsource controls; we insert a control for setting
    # the camera gain for that specific light source, and one for setting
    # the corresponding emission filter.
    def onLightControl(self, parent, sizer, light):
        if 'MultiplierGain' not in self.core.getDevicePropertyNames(self.coreCam.name):
            # Camera doesn't support gain.
            return
        curGain = self.core.getProperty(self.coreCam.name, 'MultiplierGain')
        gainButton = gui.toggleButton.ToggleButton(parent = parent,
                label = 'Gain: %s' % curGain)
        def setGain(event):
            newVal = gui.dialogs.getNumberDialog.getNumberFromUser(
                parent, title = "Select gain value",
                prompt = "Set gain:",
                default = self.core.getProperty(self.coreCam.name, 'MultiplierGain'))
            gainButton.SetLabel('Gain: %s' % newVal)
            self.lightToGain[light] = newVal
        gainButton.Bind(wx.EVT_LEFT_DOWN, setGain)
        gainButton.Bind(wx.EVT_RIGHT_DOWN, setGain)
        sizer.Add(gainButton, 1, wx.EXPAND | wx.HORIZONTAL)
        self.lightToGain[light] = curGain
        self.lightToGainButton[light] = gainButton

        filterButton = gui.toggleButton.ToggleButton(parent = parent,
                label = 'Emission: ', size = (120, 45))
        def associateFilter(name):
            self.lightToFilter[light] = name
            filterButton.SetLabel('Emission: %s' % name)
        def setFilter(event):
            eventObject = event.GetEventObject()
            menu = wx.Menu()
            for i, filterName in enumerate(self.options):
                menu.AppendCheckItem(i + 1, filterName)
                menu.Check(i + 1, self.curFilter == filterName)
                wx.EVT_MENU(eventObject, i + 1,
                        lambda event, name = filterName: associateFilter(name))
            gui.guiUtils.placeMenuAtMouse(eventObject, menu)
        filterButton.Bind(wx.EVT_LEFT_DOWN, setFilter)
        filterButton.Bind(wx.EVT_RIGHT_DOWN, setFilter)
        sizer.Add(filterButton, 1, wx.EXPAND | wx.HORIZONTAL)
        self.lightToFilterButton[light] = filterButton


    ## Take an image. We do it once per emission filter, using all the
    # lights tied to that emission filter.
    def takeImage(self, *args):
        lights = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        # Generate a mapping of emission filter to lights that use that
        # filter.
        emissionFilterToLights = {}
        for light in lights:
            if not light.getIsEnabled() or light.getIsExposingContinuously():
                continue
            if light not in self.lightToFilter:
                # Default to the current filter.
                self.lightToFilter[light] = self.curFilter
            lightFilter = self.lightToFilter[light]
            if self.lightToFilter[light] not in emissionFilterToLights:
                emissionFilterToLights[lightFilter] = []
            emissionFilterToLights[lightFilter].append(light)

        # Take images with each active filter.
        for lightFilter, lights in emissionFilterToLights.iteritems():
            # Set the filter for that light.
            self.setPosition(lightFilter)
            # Set the gain. Use the strongest gain out of all of the lights
            # used.
            gain = max([self.lightToGain[light] for light in lights])
            self.core.setProperty(self.coreCam.name, 'MultiplierGain',
                    gain)
            # Set the exposure time. Use the max exposure time of all lights,
            # since we unfortunately can't set them individually.
            exposureTime = max([light.getExposureTime() for light in lights])
            # Paranoia: the light source might potentially have a Decimal
            # for an exposure time, which MicroManager can't handle cleanly.
            self.core.setExposure(float(exposureTime))
            events.publish('nikon: prepare for image', lights)
            self.core.snapImage()
            image = self.core.getImage()
            timestamp = time.time()
            self.onImage(image, timestamp)
            # Set the lights back to continuous exposure if necessary.
            for light in lights:
                if light.getIsExposingContinuously():
                    # Simply calling setExposing(True) wouldn't do anything
                    # as the light still thinks it is exposing.
                    light.setExposing(False)
                    light.setExposing(True)


    ## Return the numeric wavelength of light seen by the camera.
    def getWavelengthForCamera(self, name, cameraName):
        filterName = self.nameToFilter[cameraName]
        return self.optionToWavelength.get(filterName, 0)


    ## Return the dye the camera sees. We've stuck the dye name into the
    # camera name; extract that back out and return it.
    def getDyeForCamera(self, name, cameraName):
        return cameraName.split('(')[1].split(')')[0]


    ## Return the color used to represent the camera. Extract the actual
    # filter this "camera" sees from its name and use that to decide the
    # color.
    def getColorForCamera(self, name, cameraName):
        for filterName in self.options:
            if filterName in cameraName:
                return DYE_TO_COLOR.get(filterName, (170, 170, 170))
        raise RuntimeError("Couldn't find the filter used for %s" % cameraName)


    ## Set the emission filter wheel position.
    def setPosition(self, label):
        try:
            self.core.setProperty('Wheel-Emission', 'State',
                    self.options.index(label))
            self.curFilter = label
            util.userConfig.setValue('EmissionFilter', self.curFilter)
            if self.menu is not None:
                self.menu.SetSelection(self.options.index(label))
            if self.drawerHandler is not None:
                events.publish('drawer change', self.drawerHandler)
        except Exception, e:
            util.logger.log.error("Failed to set emission filter position: %s" % e)
            # Drop the error, because when it happens during program startup
            # it forces a full-program reset if we raise it.


    ## The camera has generated an image; republish it based on the camera's
    # current active emission filter.
    def onImage(self, image, timestamp):
        print "Publishing image under",self.curFilter
        events.publish('new image %s (%s)' % (self.coreCam.name, self.curFilter),
                image, timestamp)
