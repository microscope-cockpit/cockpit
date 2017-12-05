## This module handles interacting with the DSP card that sends the digital and
# analog signals that control our light sources, cameras, and piezos. In 
# particular, it effectively is solely responsible for running our experiments.
# As such it's a fairly complex module. 
# 
# A few helpful features that need to be accessed from the commandline:
# 1) A window that lets you directly control the digital and analog outputs
#    of the DSP.
# >>> import devices.dsp as DSP
# >>> DSP.makeOutputWindow()
#
# 2) Create a plot describing the actions that the DSP set up in the most
#    recent experiment profile.
# >>> import devices.dsp as DSP
# >>> DSP._deviceInstance.plotProfile()
#
# 3) Manually advance the SLM forwards some number of steps; useful for when
#    it has gotten offset and is no longer "resting" on the first pattern.
# >>> import devices.dsp as DSP
# >>> DSP._deviceInstance.advanceSLM(numSteps)
# (where numSteps is an integer, the number of times to advance it).

import Pyro4
import time

import depot
import device
import events
import handlers.executor
import handlers.genericHandler
import handlers.genericPositioner
import handlers.imager
import util.threads


class ExecutorDevice(device.Device):
    def __init__(self, name, config={}):
        device.Device.__init__(self, name, config)
        ## Connection to the remote DSP computer
        self.connection = None
        ## Set of all handlers we control.
        self.handlers = set()


    ## Connect to the DSP computer.
    @util.threads.locked
    def initialize(self):
        self.connection = Pyro4.Proxy(self.uri)
        self.connection._pyroTimeout = 6
        self.connection.Abort()


    ## We care when cameras are enabled, since we control some of them 
    # via external trigger. There are also some light sources that we don't
    # control directly that we need to know about.
    def performSubscriptions(self):
        #events.subscribe('camera enable', self.toggleCamera)
        #events.subscribe('light source enable', self.toggleLightHandler)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('prepare for experiment', self.onPrepareForExperiment)

    ## As a side-effect of setting our initial positions, we will also
    # publish them. We want the Z piezo to be in the middle of its range
    # of motion.
    def makeInitialPublications(self):
        pass

    ## User clicked the abort button.
    def onAbort(self):
        self.connection.Abort()
        # Various threads could be waiting for a 'DSP done' event, preventing
        # new DSP actions from starting after an abort.
        events.publish("DSP done")


    @util.threads.locked
    def finalizeInitialization(self):
        # Tell the remote DSP computer how to talk to us.
        server = depot.getHandlersOfType(depot.SERVER)[0]
        self.receiveUri = server.register(self.receiveData)
        self.connection.receiveClient(self.receiveUri)


    ## We control which light sources are active, as well as a set of 
    # stage motion piezos. 
    def getHandlers(self):
        result = []
        h = handlers.executor.AnalogDigitalExecutorHandler(
            "DSP", "executor",
            {'examineActions': lambda *args: None,
             'executeTable': self.executeTable,
             'readDigital': self.connection.ReadDigital,
             'writeDigital': self.connection.WriteDigital,
             'getAnalog': self.connection.ReadPosition,
             'setAnalog': self.connection.MoveAbsoluteADU,
             },
            dlines=16, alines=4)

        result.append(h)

        # The takeImage behaviour is now on the handler. It might be better to
        # have hybrid handlers with multiple inheritance, but that would need
        # an overhaul of how depot determines handler types.
        result.append(handlers.imager.ImagerHandler(
            "DSP imager", "imager",
            {'takeImage': h.takeImage}))

        self.handlers = set(result)
        return result


    ## Receive data from the DSP computer.
    def receiveData(self, action, *args):
        if action.lower() == 'dsp done':
            events.publish("DSP done")


    def triggerNow(self, line, dt=0.01):
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)
        time.sleep(dt)
        self.connection.WriteDigital(self.connection.ReadDigital() ^ line)


    ## Prepare to run an experiment.
    def onPrepareForExperiment(self, *args):
        # Ensure remote has the correct URI set for sending data/notifications.
        self.connection.receiveClient(self.receiveUri)


    ## Actually execute the events in an experiment ActionTable, starting at
    # startIndex and proceeding up to but not through stopIndex.
    def executeTable(self, name, table, startIndex, stopIndex, numReps, 
            repDuration):
        # Take time and arguments (i.e. omit handler) from table to generate actions.
        t0 = float(table[startIndex][0])
        actions = [(float(row[0])-t0,) + tuple(row[2:]) for row in table[startIndex:stopIndex]]
        # If there are repeats, add an extra action to wait until repDuration expired.
        if repDuration is not None:
            repDuration = float(repDuration)
            if actions[-1][0] < repDuration:
                # Repeat the last event at t0 + repDuration
                actions.append( (t0+repDuration,) + tuple(actions[-1][1:]) )
        events.publish('update status light', 'device waiting',
                'Waiting for\nDSP to finish', (255, 255, 0))
        self.connection.PrepareActions(actions, numReps)
        events.executeAndWaitFor("DSP done", self.connection.RunActions)
        events.publish('experiment execution')
        return


        ## Debugging function: set the digital output for the DSP.
    def setDigital(self, value):
        self.connection.WriteDigital(value)