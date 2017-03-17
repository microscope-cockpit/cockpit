import device
import stage
import events
import gui.toggleButton
import handlers.genericPositioner
import handlers.stagePositioner
import util.connection
import interfaces

import numpy
import threading
import time
import wx
import copy

from config import config
CLASS_NAME = 'NanomoverDevice'
CONFIG_NAME = 'nanomover'
LIMITS_PAT = r"(?P<limits>\(\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*\,\s*[-]?\d*\s*\)\s*,\s*\(\s*[-]?\d*\s*,\s*[-]?\d*\s*\)\s*\))"

class NanomoverDevice(stage.StageDevice):
    def __init__(self):
        device.Device.__init__(self)
        ## Current stage position information.
        self.curPosition = [14500, 14500, 14500]
        ## Connection to the Nanomover controller program.
        self.connection = None
        # Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering (1: Y, 2: X,0: Z)
        self.axisMapper = {0: 0, 1: 1, 2: 2}
        ## Cached copy of the stage's position. Initialized to an impossible
        # value; this will be modified in initialize.
        self.positionCache = (10, 10, 10)
        ## Maps cockpit axis ordering to a +-1 multiplier to apply to motion,
        # since some of our axes are flipped.
        self.axisSignMapper = {0: 1, 1: 1, 2: 1}
        ## Time of last action using the piezo; used for tracking if we should
        # disable closed loop.
         
        self.isActive = config.has_section(CONFIG_NAME)
        if self.isActive:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))
            self.timeout = config.getfloat(CONFIG_NAME, 'timeout')
            try :
                limitString = config.get(CONFIG_NAME, 'softlimits')
                parsed = re.search(LIMITS_PAT, limitString)
                if not parsed:
                    # Could not parse config entry.
                    raise Exception('Bad config: Nanomover Limits.')
                    # No transform tuple
                else:    
                    lstr = parsed.groupdict()['limits']
                    self.softlimits=eval(lstr)
                    self.safeties=eval(lstr)
            except:
                print "No softlimits section setting default limits"
                self.softlimits = [[0, 25000],
                                   [0, 25000],
                                   [7300, 25000]]
                self.safeties = [[0, 25000],
                                   [0, 25000],
                                   [7300, 25000]]

            #a usful middle position for after a home
            self.middleXY=( (self.safeties[0][1]-self.safeties[0][0])/2.0,
                            (self.safeties[0][1]-self.safeties[0][0])/2.0)
                #            events.subscribe('user logout', self.onLogout)
            events.subscribe('user abort', self.onAbort)
#            events.subscribe('macro stage xy draw', self.onMacroStagePaint)
            events.subscribe('cockpit initialization complete',
                    self.promptExerciseStage)

        

    def initialize(self):
        self.connection = util.connection.Connection(
                'nano', self.ipAddress, self.port)
        self.connection.connect(self.receiveData)
        self.curPosition[:] = self.connection.connection.posXYZ_OMX()
        if self.curPosition == [0,0,0]:
            print "Homing Nanomover"
            self.connection.connection.startOMX()
            self.home()
            interfaces.stageMover.goToXY(self.middleXY, shouldBlock = True)

    ## We want to periodically exercise the XY stage to spread the grease
    # around on its bearings; check how long it's been since the stage was
    # last exercised, and prompt the user if it's been more than a week.
    def promptExerciseStage(self):
        lastExerciseTimestamp = util.userConfig.getValue(
                'NanomoverLastExerciseTimestamp',
                isGlobal = True, default = 0)
        curTime = time.time()
        delay = curTime - lastExerciseTimestamp
        daysPassed = delay / float(24 * 60 * 60)
        if (daysPassed > 7 and
                gui.guiUtils.getUserPermission(
                    ("It has been %.1f days since " % daysPassed) +
                    "the stage was last exercised. Please exercise " +
                    "the stage regularly.\n\nExercise stage?",
                    "Please exercise the stage")):
            # Move to the middle of the stage, then to one corner, then to
            # the opposite corner, repeat a few times, then back to the middle,
            # then to where we started from. Positions are actually backed off
            # slightly from the true safeties. Moving to the middle is
            # necessary to avoid the banned rectangles, in case the stage is
            # in them when we start.
            initialPos = tuple(self.positionCache)
#            interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            for i in xrange(5):
                print "Rep %d of 5..." % i
                for position in self.softlimits[0:2]:
                    interfaces.stageMover.goToXY(position, shouldBlock = True)
            interfaces.stageMover.goToXY(self.middleXY, shouldBlock = True)
            interfaces.stageMover.goToXY(initialPos, shouldBlock = True)
            print "Exercising complete. Thank you!"
            
            util.userConfig.setValue('NanomoverLastExerciseTimestamp',
                    time.time(), isGlobal = True)



    def performSubscriptions(self):
        events.subscribe('user abort', self.onAbort)


    def makeInitialPublications(self):
        events.publish('new status light', 'stage vertical position', '')
        self.publishPosition()
        self.sendXYPositionUpdates()

    ## The XY Macro Stage view is painting itself; draw the banned
    # rectangles as pink excluded zones.
#    def onMacroStagePaint(self, stage):
#        glColor3f(1, .6, .6)
#        glBegin(GL_QUADS)
#        for (x1, y1), (x2, y2) in BANNED_RECTANGLES:
#            stage.scaledVertex(x1, y1)
#            stage.scaledVertex(x1, y2)
#            stage.scaledVertex(x2, y2)
#            stage.scaledVertex(x2, y1)
#        glEnd()


    def getHandlers(self):
        result = []
        for axis in xrange(3):
            stepSizes = [.1, .2, .5, 1, 2, 5, 10, 50, 100, 500, 1000]
            if axis == 2:
                # Add smaller step sizes for the Z axis.
                stepSizes = [.01, .02, .05] + stepSizes
            lowLimit, highLimit = self.safeties[axis]
            softLowLimit , softHighLimit = self.softlimits[axis]
            result.append(handlers.stagePositioner.PositionerHandler(
                "%d nanomover" % axis, "%d stage motion" % axis, False, 
                {'moveAbsolute': self.moveAbsolute, 
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition,
                    'setSafety': self.setSafety}, 
                axis, stepSizes, 3, 
                (softLowLimit, softHighLimit), (lowLimit, highLimit)))
        return result


    ## Publish the current stage position, and update the status light that
    # shows roughly where the stage is vertically.
    def publishPosition(self):
        for i in xrange(3):
            events.publish('stage mover', '%d nanomover' % i, i, 
                    (self.curPosition[i]))
        label = 'Stage up'
        color = (170, 170, 170)
        if 10000 < self.curPosition[2] < 16000:
            label = 'Stage middle'
            color = (255, 255, 0)
        elif self.curPosition[2] < 10000:
            label = 'Stage DOWN'
            color = (255, 0, 0)
        events.publish('update status light', 'stage vertical position',
                label, color)


    ## Send updates on the XY stage's position, until it stops moving.
    @util.threads.callInNewThread
    def sendXYPositionUpdates(self):
        while True:
            prevX, prevY = self.positionCache[:2]
            x, y, z = self.getPosition(shouldUseCache = False)
            delta = abs(x - prevX) + abs(y - prevY)
            if delta < 2:
                # No movement since last time; done moving.
                for axis in [0, 1]:
                    events.publish('stage stopped', '%d nanomover' % axis)
                return
            for axis, val in enumerate([x, y]):
                events.publish('stage mover', '%d nanomover' % axis, 
                               axis, self.axisSignMapper[axis] * val)
            time.sleep(.1)

    def getPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            position = self.connection.connection.posXYZ_OMX()
            x = float(position[self.axisMapper[0]]) * self.axisSignMapper[0]
            y = float(position[self.axisMapper[1]]) * self.axisSignMapper[1]
            z = float(position[self.axisMapper[2]]) * self.axisSignMapper[2]
            self.positionCache = (x, y, z)
        if axis is None:
            return self.positionCache
        return self.positionCache[axis]


    ## Receive information from the Nanomover control program.
    def receiveData(self, *args):
        if args[0] == 'nanoMotionStatus':
            self.curPosition[:] = args[1]
            self.publishPosition()
            if args[-1] == 'allStopped':
                for i in xrange(3):
                    events.publish('stage stopped', '%d nanomover' % i)


    ## Move a specific axis to a given position.
    def moveAbsolute(self, axis, pos):
        self.sendXYPositionUpdates()
        self.connection.connection.moveOMX_axis(axis, pos)



    ## Move a specific axis by a given amount.
    def moveRelative(self, axis, delta):
        self.sendXYPositionUpdates()
        self.connection.connection.moveOMX_dAxis(axis, delta)


    ## Set the soft motion limit (min or max) for the specified axis.
    def setSafety(self, axis, value, isMax):
        connection = self.connection.connection
        if isMax:
            connection.setSafetyMaxOMX(axis, value)
        else:
            connection.setSafetyMinOMX(axis, value)


    ## User clicked the abort button; halt motion.
    def onAbort(self, *args):
        self.connection.connection.stopOMX()

    #function to home stage if needed.
    def home(self):
        #keep a copy of the softlimits.
#        realSoftlimits= copy.copy(self.softlimits)
#        self.softlimits = [[-25000, 25000],
#                           [-25000, 25000],
#                           [7300, 50000]]
        #home the stage which moves to lrage negative positon until it 
        #hits the hard limit switch 
        self.connection.connection.findHome_OMX()
        self.sendXYPositionUpdates()
        self.positionCache = self.getPosition(shouldUseCache = False)
        #reset softlimits to their original value
#        self.softlimits=realSoftlimits

