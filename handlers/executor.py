import depot
import deviceHandler
import events
from handlers.genericPositioner import GenericPositionerHandler
import operator
import time
import util
import gui
import wx

## This handler is responsible for executing portions of experiments.
class ExecutorHandler(deviceHandler.DeviceHandler):
    ## callbacks must include the following:
    # - examineActions(name, table): Perform any necessary validation or
    #   modification of the experiment's ActionTable.
    # - executeTable(name, table, startIndex, stopIndex): Actually perform
    #   actions through the specified lines in the ActionTable.
    def __init__(self, name, groupName, callbacks, dlines=None, alines=None):
        # \param name: handler name
        # \param groupname: handler and device group name
        # \param callbacks: callbacks, as above
        # \param dlines: optional, number of digital lines
        # \param alines: optional, number of analogue lines
        # Note that even though this device is directly involved in running
        # experiments, it is never itself a part of an experiment, so 
        # we pass False for isEligibleForExperiments here.
        deviceHandler.DeviceHandler.__init__(self, name, groupName, False,
                callbacks, depot.EXECUTOR)
        # Base class contains empty dicts used by mixins so that methods like
        # getNumRunnableLines can be implemented here for all mixin combos. This
        # works just great, but is probably a horrible abuse of OOP. It might be
        # cleaner to have a single list of clients.
        self.digitalClients = {}
        self.analogClients = {}
        # Number of digital and analogue lines.
        self._dlines = dlines
        self._alines = alines
        if not isinstance(self, DigitalMixin):
            self.registerDigital = self._raiseNoDigitalException
            self.getDigital = self._raiseNoDigitalException
            self.setDigital = self._raiseNoDigitalException
            self.readDigital = self._raiseNoDigitalException
            self.writeDigital = self._raiseNoDigitalException
            self.triggerDigital = self._raiseNoDigitalException
        if not isinstance(self, AnalogMixin):
            self.registerAnalog = self._raiseNoAnalogException
            self.setAnalog = self._raiseNoAnalogException
            self.getAnalog = self._raiseNoAnalogException
            self.setAnalogClient = self._raiseNoAnalogException
            self.getAnalogClient = self._raiseNoAnalogException
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)
        events.subscribe('cleanup after experiment', self.cleanupAfterExperiment)

    def examineActions(self, table):
        return self.callbacks['examineActions'](table)

    def getNumRunnableLines(self, table, index):
        ## Return number of lines this handler can run.
        count = 0
        for time, handler, parameter in table[index:]:
            # Check for analog and digital devices we control.
            if (handler is not self and
                   handler not in self.digitalClients and
                   handler not in self.analogClients):
                # Found a device we don't control.
                break
            count += 1
        return count

    def _raiseNoDigitalException(self, *args, **kwargs):
        raise Exception("Digital lines not supported.")

    def _raiseNoAnalogException(self, *args, **kwargs):
        raise Exception("Analog lines not supported.")

    ## Run a portion of a table describing the actions to perform in a given
    # experiment.
    # \param table An ActionTable instance.
    # \param startIndex Index of the first entry in the table to run.
    # \param stopIndex Index of the entry before which we stop (i.e. it is
    #        not performed).
    # \param numReps Number of times to iterate the execution.
    # \param repDuration Amount of time to wait between reps, or None for no
    #        wait time. 
    def executeTable(self, table, startIndex, stopIndex, numReps, repDuration):
        # The actions between startIndex and stopIndex may include actions for
        # this handler, or for this handler's clients. All actions are
        # ultimately carried out by this handler, so we need to parse the
        # table to replace client actions, resulting in a table of
        # (time, (analogStage, digitalState)).
        if isinstance(self, DigitalMixin):
            dstate = self.readDigital()
        else:
            dstate = None
        if isinstance(self, AnalogMixin):
            astate = [self.getAnalogLine(line) for line in range(self._alines)]
        else:
            astate = None

        actions = []

        tPrev = None
        hPrev = None
        argsPrev = None

        for i in range(startIndex, stopIndex):
            t, h, args = table[i]
            if h in self.analogClients:
                # update analog state
                lineHandler = self.analogClients[h]
                astate[lineHandler.line] = lineHandler.posToNative(args)
            elif h in self.digitalClients:
                # set/clear appropriate bit
                change = 1 << self.digitalClients[h]
                # args contains new bit state
                if args:
                    dstate |= change
                else:
                    dstate = dstate & (2**self._dlines - 1) - (change)

            # Check for simultaneous actions.
            if tPrev is not None and t == tPrev:
                if h not in hPrev:
                    # Update last action to merge actions at same timepoint.
                    actions[-1] = (t, self, (dstate, astate[:]))
                    # Add handler and args to list for next check.
                    hPrev.append(h)
                    argsPrev.append(args)
                elif args == argsPrev[hPrev.index(h)]:
                    # Just a duplicate entry
                    continue
                else:
                    # Simultaneous, different actions with same handler.
                    raise Exception("Simultaneous actions with same hander, %s." % h)
            else:
                # Append new action.
                actions.append((t, self, (dstate, astate[:])))
                # Reinitialise hPrev and argsPrev for next check.
                hPrev, argsPrev = [h], [args]
                tPrev = t

        events.publish('update status light', 'device waiting',
                       'Waiting for\n%s to finish' % self.name, (255, 255, 0))

        return self.callbacks['executeTable'](self.name, actions, 0,
                len(actions), numReps, repDuration)

    ## Debugging function: display ExecutorOutputWindow.
    def showDebugWindow(self):
        # Ensure only a single instance of the window.
        global _windowInstance
        window = globals().get('_windowInstance')
        if window:
            try:
                window.Raise()
                return None
            except:
                pass
        # If we get this far, we need to create a new window.
        _windowInstance = ExecutorDebugWindow(self, parent=wx.GetApp().GetTopWindow())
        _windowInstance.Show()

    def onPrepareForExperiment(self, experiment):
        # This smells sketchy, but does exactly what we need: run
        # the method on all mixins contributing to a hybrid class.
        # Could do achieve the same by having mixins append to a list
        # of actions to call on certain events.
        for c in self.__class__.__mro__[1:]:
            if hasattr(c, '_onPrepareForExperiment'):
                c._onPrepareForExperiment(self)

    def cleanupAfterExperiment(self, isCleanupFinal=True):
        # See comments in onPrepareForExperiment
        for c in self.__class__.__mro__[1:]:
            if hasattr(c, '_cleanupAfterExperiment'):
                c._cleanupAfterExperiment(self, isCleanupFinal)


class DigitalMixin(object):
    ## Digital handler mixin.

    ## Register a client device that is connected to one of our lines.
    def registerDigital(self, client, line):
        self.digitalClients[client] = int(line)

    ## Set or clear a single line.
    def setDigital(self, line, state):
        if line is None:
            return
        if self.callbacks.get('setDigital', None):
            self.callbacks['setDigital'](line, state)
        else:
            oldstate = self.readDigital()
            if state:
                newstate = oldstate | 1<<line
            else:
                newstate = oldstate & (2**self._dlines - 1) - (1<<line)
            self.writeDigital(newstate)

    def writeDigital(self, state):
        self.callbacks['writeDigital'](state)

    def readDigital(self):
        return self.callbacks['readDigital']()

    def triggerDigital(self, client, dt=0.01):
        ## Trigger a client line now.
        line = self.digitalClients.get(client, None)
        if line:
            self.setDigital(line, True)
            time.sleep(dt)
            self.setDigital(line, False)

    @property
    def activeLights(self):
        return filter(lambda h: h.deviceType==depot.LIGHT_TOGGLE
                                and h.getIsEnabled(),
                      self.digitalClients)

    @property
    def activeCameras(self):
        return filter(lambda h: h.deviceType == depot.CAMERA
                                and h.getIsEnabled(),
                      self.digitalClients)

    def takeImage(self):
        if not self.digitalClients:
            # No triggered devices registered.
            return
        camlines = sum([1<<self.digitalClients[cam] for cam in self.activeCameras])

        if camlines == 0:
            # No cameras to be triggered.
            return

        ltpairs = []
        for light in self.activeLights:
            lline = 1 << self.digitalClients[light]
            ltime = light.getExposureTime()
            ltpairs.append((lline, ltime))

        # Sort by exposure time
        ltpairs.sort(key = lambda item: item[1])

        # Generate a sequence of (time, digital state)
        # TODO: currently uses bulb exposure; should support other modes.
        if ltpairs:
            # Start by all active cameras and lights.
            state = camlines | reduce(operator.ior, zip(*ltpairs)[0])
            seq = [(0, state)]
            # Switch off each light as its exposure time expires.
            for  lline, ltime in ltpairs:
                state -= lline
                seq.append( (ltime, state))
        else:
            # No lights. Just trigger the cameras.
            seq = [(0, camlines)]
        ambient = depot.getHandlerWithName('ambient')
        # If ambient light is enabled, extend exposure if necessary.
        if ambient.getIsEnabled():
            t = ambient.getExposureTime()
            if t > seq[-1][0]:
                seq.append((ambient.getExposureTime(), 0))
        # Switch all lights and cameras off.
        seq.append( (seq[-1][0] + 1, 0) )
        if self.callbacks.get('runSequence', None):
            self.callbacks['runSequence'](seq)
        else:
            self.softSequence(seq)

    def writeWithMask(self, mask, state):
        initial = self.readDigital()
        final = (initial & ~mask) | state
        self.writeDigital( final )

    @util.threads.callInNewThread
    def softSequence(self, seq):
        # Mask of the bits that we toggle
        mask = reduce(operator.ior, zip(*seq)[1])
        entryState = self.readDigital()
        for t, state in seq:
            time.sleep(t/1000.)
            self.writeWithMask(mask, state)
        self.writeDigital(entryState)


class AnalogMixin(object):
    ## Analog handler mixin.
    # Consider output 'level' in volts, amps or ADUS, and input
    # 'position' in experimental units (e.g. um or deg).
    # level = gain * (offset + position)
    # gain is in units of volts, amps or ADUS per experimental unit.
    # offset is in experimental units.

    def registerAnalog(self, client, line, offset=0, gain=1, movementTimeFunc=None):
        ## Register a client device that is connected to one of our lines.
        # Returns an AnalogLineHandler for that line.
        h = AnalogLineHandler(client.name, self.name + ' analogs',
                              self, int(line), offset, gain, movementTimeFunc)
        self.analogClients[client] = h
        return h

    def setAnalogLine(self, line, level):
        ## Set analog output of line to level.
        self.callbacks['setAnalog'](line, level)

    def getAnalogLine(self, line):
        ## Get level of analog line.
        return self.callbacks['getAnalog'](line)

    def _onPrepareForExperiment(self):
        for client in self.analogClients:
            self.analogClients[client].savePosition()

    def _cleanupAfterExperiment(self, isCleanupFinal=True):
        if isCleanupFinal:
            for client in self.analogClients:
                self.analogClients[client].restorePosition()

    # def setClientPosition(self, client, value):
    #     ## Scale a client position to an analog level and set that level.
    #     line, offset, gain = self.analogClients[client]
    #     self.callbacks['setAnalog'](line, gain * (offset + value))
    #
    # def getClientPosition(self, client):
    #     ## Fetch level for a client, and scale to a client position.
    #     line, offset, gain = self.analogClients[client]
    #     raw = self.callbacks['getAnalog'](line)
    #     return (raw / gain) - offset


class AnalogLineHandler(GenericPositionerHandler):
    ## A type of GenericPositioner for analog outputs.
    def __init__(self, name, groupName, asource, line, offset, gain, movementTimeFunc):
        # Indexed positions. Can be a dict if wavelength-independent, or
        # a mapping of wavelengths (as floats or ints) to lists of same length.
        self.positions = []
        # Scaling parameters
        self.gain = gain
        self.offset = offset
        # Line, required when executing table.
        self.line = line
        # Saved position
        self._savedPos = None
        # Set up callbacks used by GenericPositionHandler methods.
        self.callbacks = {}
        self.callbacks['moveAbsolute'] = lambda pos: asource.setAnalogLine(line, self.posToNative(pos))
        self.callbacks['getPosition'] = lambda: self.nativeToPos(asource.getAnalogLine(line))
        self.callbacks['getMovementTime'] = movementTimeFunc
        deviceHandler.DeviceHandler.__init__(self, name, groupName, True,
                                             self.callbacks, depot.GENERIC_POSITIONER)

    def savePosition(self):
        self._savedPos = self.getPosition()

    def restorePosition(self):
        self.moveAbsolute(self._savedPos)

    def moveRelative(self, delta):
        self.callbacks['moveAbsolute'](self.callbacks['getPosition']() + delta)

    def posToNative(self, pos):
        return self.gain * (self.offset + pos)

    def nativeToPos(self, native):
        return (native / self.gain) - self.offset

    def indexedPosition(self, index, wavelength=None):
        pos = None
        if wavelength is not None and isinstance(self.positions, dict):
            wl = min(self.calib.keys(), key=lambda w: abs(w - wavelength))
            ps = self.positions[wl]
        elif isinstance(self.positions, dict):
            if self.positions.has_key(None):
                ps = self.positons[None]
            elif self.positions.has_key('default'):
                ps = self.positions['default']
        else:
            ps = self.positions
        return ps[index]


class DigitalExecutorHandler(DigitalMixin, ExecutorHandler):
    pass


class AnalogExecutorHandler(AnalogMixin, ExecutorHandler):
    pass


class AnalogDigitalExecutorHandler(AnalogMixin, DigitalMixin, ExecutorHandler):
    pass


## This debugging window allows manipulation of analogue and digital lines.
class ExecutorDebugWindow(wx.Frame):
    def __init__(self, handler, parent, *args, **kwargs):
        title = handler.name + " Executor control lines"
        wx.Frame.__init__(self, parent, title=title, *args, **kwargs)
        panel = wx.Panel(self)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 8, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        if handler._dlines is not None:
            # Digital controls
            for line in xrange(handler._dlines):
                clients = [k.name for k,v in handler.digitalClients.items() if v==line]
                if clients:
                    label = '\n'.join(clients)
                else:
                    label = str(line)
                button = gui.toggleButton.ToggleButton(
                    parent=panel, label=label,
                    activateAction=lambda line=line: handler.setDigital(line, True),
                    deactivateAction=lambda line=line: handler.setDigital(line, False),
                    size=(140, 80)
                )
                buttonSizer.Add(button, 1, wx.EXPAND)
            mainSizer.Add(buttonSizer)

            # Analog controls
            # These controls deal with hardware units, i.e. probably ADUs.
            anaSizer = wx.BoxSizer(wx.HORIZONTAL)
            for line in xrange(handler._alines):
                anaSizer.Add(wx.StaticText(panel, -1, "output %d:" % line))
                control = wx.TextCtrl(panel, -1, size=(60, -1),
                                      style=wx.TE_PROCESS_ENTER)
                control.Bind(wx.EVT_TEXT_ENTER,
                             lambda evt, line=line, ctrl=control:
                                handler.setAnalogLine(line, float(ctrl.GetValue()) ))
                                # If dealing with ADUs, float should perhaps be int,
                                # but rely on device to set correct type.
                anaSizer.Add(control, 0, wx.RIGHT, 20)
            mainSizer.Add(anaSizer)

        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())