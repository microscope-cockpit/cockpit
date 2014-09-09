## This module serves as a central coordination point for all devices. Devices
# are initialized and registered from here, and if a part of the UI wants to 
# interact with a specific kind of device, they can find it through the depot.

import util.importer

import importlib
import os

## Different eligible device handler types. These correspond 1-to-1 to
# subclasses of the DeviceHandler class.
CAMERA = "camera"
CONFIGURATOR = "configurator"
DRAWER = "drawer"
EXECUTOR = "experiment executor"
GENERIC_DEVICE = "generic device"
GENERIC_POSITIONER = "generic positioner"
IMAGER = "imager"
LIGHT_FILTER = "light filter"
LIGHT_POWER = "light power"
LIGHT_TOGGLE = "light source"
OBJECTIVE = "objective"
POWER_CONTROL = "power control"
SERVER = "server"
STAGE_POSITIONER = "stage positioner"
DEVICE_FOLDER = 'devices'


class DeviceDepot:
    ## Initialize the Depot. Find all the other modules in the "devices" 
    # directory and initialize them.
    def __init__(self):
        ## Maps modules to the devices for those modules.
        self.moduleToDevice = {}
        ## Maps devices to their handlers.
        self.deviceToHandlers = {}
        ## Maps handlers back to their devices.
        self.handlerToDevice = {}
        ## List of all device handlers for active modules.
        self.handlersList = []
        ## Maps handler device types to lists of the handlers controlling that
        # type.
        self.deviceTypeToHandlers = {}
        ## Maps handler names to handlers with those names. NB we enforce that
        # there only be one handler per name when we load the handlers.
        self.nameToHandler = {}
        ## Maps handler group names to lists of the handlers in those groups.
        self.groupNameToHandlers = {}


    ## Return the number of device modules we have to work with.
    def getNumModules(self):
        return len(util.importer.getModulesFrom(DEVICE_FOLDER,
                ['__init__', 'device', 'camera']))


    ## Instantiate all of the Device instances that front our hardware.
    # We examine all of the modules in the local directory, and try to
    # create a Device subclass from each (barring a few).
    def generateDevices(self):
        modules = util.importer.getModulesFrom(DEVICE_FOLDER, 
                ['__init__', 'device', 'camera'])
        for module in modules:
            self.loadDeviceModule(module)


    ## HACK: load any Configurator device that may be stored in a
    # "configurator.py" module. This is needed because config must be loaded
    # before any other Device, so that logfiles can be stored properly.
    def loadConfig(self):
        if os.path.exists(os.path.join(DEVICE_FOLDER, 'configurator.py')):
            path = '.'.join([DEVICE_FOLDER, 'configurator'])
            module = importlib.import_module(path)
            device = self.loadDeviceModule(module)
            if device is not None: # i.e. device is active.
                self.initDevice(device)


    ## Load the specified device module.
    def loadDeviceModule(self, module):
        if module in self.moduleToDevice:
            # Specially loaded this module earlier (e.g. for config).
            return
        instance = module.__dict__[module.CLASS_NAME]()
        if instance.getIsActive():
            self.moduleToDevice[module] = instance
            # For debugging purposes it can be handy to have easy access
            # to the device instance without needing to go through the
            # Depot, so we put a copy here.
            module._deviceInstance = instance
            return instance


    ## Call the initialize() method for each registered device, then get
    # the device's Handler instances and insert them into our various
    # containers. Yield the names of the modules holding the Devices as we go.
    def initialize(self):
        self.generateDevices()
        # Initialize devices in order of their priorities
        modulesAndDevices = sorted(self.moduleToDevice.items(),
                key = lambda pair: pair[1].priority)
        for module, device in modulesAndDevices:
            # Check if we've already initialized the device (currently only
            # an issue for Configurators).
            if device not in self.deviceToHandlers:
                yield module.__name__
                self.initDevice(device)
        self.finalizeInitialization()


    ## Initialize a Device.
    def initDevice(self, device):
        if device.priority == float('inf'):
            # This is a dummy device.  Figure out if it's needed.
            needDummy = True
            try:
                deviceType = device.deviceType
            except:
                raise Exception("Dummy device %s must declare its deviceType."
                                 % (device.__class__))
                needDummy = False

            if ((device.deviceType == STAGE_POSITIONER)
                & self.deviceTypeToHandlers.has_key(STAGE_POSITIONER) ):
                # If we already have a handler for this axis, then
                # we don't need the dummy handler.
                try:
                    axes = device.axes
                except:
                    raise Exception("Dummy mover device must declare its axes.")
                    needDummy = False

                if self.deviceTypeToHandlers.has_key(STAGE_POSITIONER):
                    for other_handler in self.deviceTypeToHandlers[STAGE_POSITIONER]:
                        if other_handler.axis in axes:
                            # There is already a handler for this axis.
                            needDummy = False
                            
            elif self.deviceTypeToHandlers.has_key(deviceType):
                    # For anything else, we don't need a dummy handler if
                    # we already have any handlers of this type.
                    needDummy = False

            if not needDummy:
                print "Skipping dummy module: %s." % device.__module__
                return
            else:
                print "Using dummy module: %s." % device.__module__

        # Initialize and perform subscriptions
        # *after* we know the device is required.
        device.initialize()
        device.performSubscriptions()

        handlers = device.getHandlers()
        self.deviceToHandlers[device] = handlers
        self.handlersList.extend(handlers)
        for handler in handlers:
            if handler.deviceType not in self.deviceTypeToHandlers:
                self.deviceTypeToHandlers[handler.deviceType] = []
            self.deviceTypeToHandlers[handler.deviceType].append(handler)
            if handler.groupName not in self.groupNameToHandlers:
                self.groupNameToHandlers[handler.groupName] = []
            if handler.name in self.nameToHandler:
                # We enforce unique names.
                otherHandler = self.nameToHandler[handler.name]
                otherDevice = self.handlerToDevice[otherHandler]
                raise RuntimeError("Multiple handlers with the same name [%s] from devices [%s] and [%s]" %
                    (handler.name, str(device), str(otherDevice)))
            self.nameToHandler[handler.name] = handler
            self.handlerToDevice[handler] = device
            
            self.groupNameToHandlers[handler.groupName].append(handler)

    

    ## Let each device publish any initial events it needs. It's assumed this
    # is called after all the handlers have set up their UIs, so that they can
    # be adjusted to match the current configuration. 
    def makeInitialPublications(self):
        for device in self.moduleToDevice.values():
            device.makeInitialPublications()
        for handler in self.handlersList:
            handler.makeInitialPublications()


    ## Do any extra initialization needed now that everything is properly
    # set up.
    def finalizeInitialization(self):
        for device in sorted(self.moduleToDevice.values(), key = lambda d: d.priority):
            device.finalizeInitialization()
        for handler in self.handlersList:
            handler.finalizeInitialization()
        

    ## Return a mapping of axis to a sorted list of positioners for that axis.
    # We sort by range of motion, with the largest range coming first in the
    # list.
    def getSortedStageMovers(self):
        movers = self.deviceTypeToHandlers.get(STAGE_POSITIONER, [])
        axisToMovers = {}
        for mover in movers:
            if mover.axis not in axisToMovers:
                axisToMovers[mover.axis] = []
            axisToMovers[mover.axis].append(mover)

        for axis, handlers in axisToMovers.iteritems():
            handlers.sort(reverse = True,
                    key = lambda a: a.getHardLimits()[1] - a.getHardLimits()[0]
            )
        return axisToMovers



## Global singleton
deviceDepot = DeviceDepot()


## Simple passthrough
def loadConfig():
    deviceDepot.loadConfig()


## Simple passthrough.
def getNumModules():
    return deviceDepot.getNumModules()


## Simple passthrough.
def initialize():
    for module in deviceDepot.initialize():
        yield module


## Simple passthrough.
def makeInitialPublications():
    deviceDepot.makeInitialPublications()


## Return the handler with the specified name.
def getHandlerWithName(name):
    return deviceDepot.nameToHandler.get(name, None)


## Return all registered device handlers of the appropriate type.
def getHandlersOfType(deviceType):
    return deviceDepot.deviceTypeToHandlers.get(deviceType, [])


## Return all registered device handlers in the appropriate group.
def getHandlersInGroup(groupName):
    return deviceDepot.groupNameToHandlers.get(groupName, [])


## Get all registered device handlers.
def getAllHandlers():
    return deviceDepot.nameToHandler.values()


## Get all registered devices.
def getAllDevices():
    return deviceDepot.moduleToDevice.values()


## Simple passthrough.
def getSortedStageMovers():
    return deviceDepot.getSortedStageMovers()


## Get all cameras that are currently in use.
def getActiveCameras():
    cameras = getHandlersOfType(CAMERA)
    result = []
    for camera in cameras:
        if camera.getIsEnabled():
            result.append(camera)
    return result


## Get the Device instance associated with the given module.
def getDevice(module):
    return deviceDepot.moduleToDevice[module]


## Debugging function: reload the specified module to pick up any changes to 
# the code. This requires us to cleanly shut down the associated Device and 
# then re-create it without disturbing the associated Handlers (which may be
# referred to in any number of places in the rest of the code). Most Devices
# won't support this (reflected by the base Device class's shutdown() function
# raising an exception). 
def reloadModule(module):
    device = deviceDepot.moduleToDevice[module]
    handlers = deviceDepot.deviceToHandlers[device]
    device.shutdown()
    reload(module)
    newDevice = module.__dict__[module.CLASS_NAME]()
    newDevice.initFromOldDevice(device, handlers)


