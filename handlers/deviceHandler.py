import events
import threading
import util.threads
from itertools import ifilter

## A DeviceHandler acts as the interface between the GUI and the device module.
# In other words, it tells the GUI what the device does, and translates GUI
# events into commands for the device. A variety of stock DeviceHandler 
# subclasses are available for representing common types of hardware. In order
# to make your hardware accessible to the UI, you need to make a Device, and
# implement its getHandlers() method so that it returns a list of
# DeviceHandlers. 
#
# The device handler now supports multiple UI controls to en/disable those
# devices that support this behaviour.
# To add a toggle control anywhere in the UI:
#  * Create a control with the method onEnabledEvent(enabled) that updates
#    the control appearance depending on the device state. The function should
#    import STATES and respond accordingly to each case.
#  * Register the control with handler(addListener) so it receives
#    device state updates.
#  * Bind the control to handler(toggleState) so it can control device state.

## Device states
class STATES():
    error = -1
    disabled = 0
    enabled = 1
    enabling = 2


class DeviceHandler(object):
    ## \param name The name of the device being controlled. This should be
    #         unique, as it is used to indicate the specific DeviceHandler
    #         in many callback functions. 
    # \param groupName The name of the group of objects this object falls
    #        under. Multiple DeviceHandlers can correspond to a single group
    #        when their purpose is similar.
    # \param callbacks Mapping of strings to functions. Each Handler has a 
    #        different selection of functions that must be filled in by the 
    #        Device that created it. Refer to the Handler's constructor.
    # \param deviceType Type of device this is; each subclass of DeviceHandler
    #        should have a distinct deviceType. Normal users don't need to 
    #        worry about this as it is provided automatically by the 
    #        DeviceHandler subclass. 
    # \param isEligibleForExperiments True if the device can be used in
    #        experiments (i.e. data collections).
    @staticmethod
    def cached(f):
        def wrapper(self, *args, **kwargs):
            key = (f, args, frozenset(sorted(kwargs.items())))
            # Previously, I checked for key existence and, if it wasn't
            # found, added the key and value to the cache, then returned
            # self.__cache[key]. If another thread calls reset_cache 
            # between the cache assignment and the return, this can
            # cause a KeyError, so instead I now put the result in a 
            # local variable, cache it, then return the local.
            try:
                return self.__cache[key]
            except KeyError:
                result = f(self, *args, **kwargs)
                self.__cache[key] = result
                return result
        return wrapper


    @staticmethod
    def reset_cache(f=None):
        def wrapper(self, *args, **kwargs):
            self.__cache = {}
            if f is None:
                return f
            else:
                return f(self, *args)
        return wrapper


    def __init__(self, name, groupName, isEligibleForExperiments, callbacks, 
            deviceType):
        self.__cache = {}
        self.name = name
        self.groupName = groupName
        self.callbacks = callbacks
        self.isEligibleForExperiments = isEligibleForExperiments
        self.deviceType = deviceType
        # A set of controls that listen for device events.
        self.listeners = None
        self.enableLock = threading.Lock()
        self.clear_cache = self.__cache.clear

    ## Return a string that identifies the device.
    def getIdentifier(self):
        return "%s:%s" % (self.deviceType, self.name)

    ## Construct any necessary UI widgets for this Device to perform its job.
    # Return a WX sizer holding the result, or None if nothing is to be 
    # inserted into the parent object. 
    # \param parent The WX object that will own the UI.
    def makeUI(self, parent):
        if 'makeUI' in self.callbacks:
            return self.callbacks['makeUI'](parent)
        else:
            return None


    ## Publish any necessary events to declare our initial configuration to 
    # anything that cares. At this point, all device handlers should be 
    # initialized.
    def makeInitialPublications(self):
        pass


    ## Do any final initaliaziton actions, now that all devices are set up,
    # all subscriptions have been made, and all initial publications are done.
    def finalizeInitialization(self):
        pass


    ## Return True if we can be used during experiments.
    def getIsEligibleForExperiments(self):
        return self.isEligibleForExperiments


    ## Generate a string of information that we want to save into the 
    # experiment file's header. There's limited space (800 characters) so
    # only important information should be preserved. This callback is 
    # optional; by default nothing is generated.
    def getSavefileInfo(self):
        if 'getSavefileInfo' in self.callbacks:
            return self.callbacks['getSavefileInfo'](self.name)
        return ''


    ## Do any necessary cleanup when an experiment is finished.
    # \param isCleanupFinal This boolean indicates if we're about to leap into
    #        a followup experiment. In that situation, some cleanup steps may
    #        be unnecessary and should be omitted for performance reasons.
    def cleanupAfterExperiment(self, isCleanupFinal = True):
        pass


    ## Debugging: print some pertinent info.
    def __repr__(self):
        return "<%s named %s in group %s>" % (self.deviceType, self.name, self.groupName)


    ## Add a listener to our set of listeners.
    def addListener(self, listener):
        # If this is our first listener, subscribe this handler to enable event.
        if self.listeners is None:
            self.listeners = set()
            events.subscribe(self.deviceType + ' enable', self.notifyListeners)
        self.listeners.add(listener)


    ## Notify listeners that our device's state has changed.
    def notifyListeners(self, source, *args, **kwargs):
        if source is not self:
            return
        if args[0] is True:
            state = STATES.enabled
        elif args[0] is False:
            state = STATES.disabled
        else:
            state = args[0]
        # Update our set of listeners to remove those that are no longer valid.
        # (e.g. UI elements that have been destroyed)
        self.listeners.difference_update(
            [thing for thing in ifilter(lambda x: not(x), self.listeners)])
        # Notify valid listeners.
        for thing in self.listeners:
            try:
                thing.onEnabledEvent(state)
            except:
                raise


    ## A function that any control can call to toggle enabled/disabled state.
    @util.threads.callInNewThread
    def toggleState(self, *args, **kwargs):
        if not all([hasattr(self, 'setEnabled'), hasattr(self, 'getIsEnabled')]):
            raise Exception('toggleState dependencies not implemented for %s.' % self.name)
        # Do nothing if lock locked as en/disable already in progress.
        if self.enableLock.acquire(False):
            try:
                self.notifyListeners(self, STATES.enabling)
                self.setEnabled(not(self.getIsEnabled()))
            except Exception as e:
                self.notifyListeners(self, STATES.error)
                raise Exception('Problem encountered en/disabling %s:\n%s' % (self.name, e))
            finally:
                self.enableLock.release()
