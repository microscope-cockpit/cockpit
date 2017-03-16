import device
import events
import gui.toggleButton
import handlers.genericPositioner
import handlers.stagePositioner
import util.connection

import numpy
import threading
import time
import wx

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
        ## Soft safety motion limits. 
#        self.safeties = [[4000, 25000], [4000, 25000], [7300, 25000]]
        # Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering (1: Y, 2: X,0: Z)
 
        self.axisMapper = {0: 2, 1: 1, 2: 0}
        ## Maps cockpit axis ordering to a +-1 multiplier to apply to motion,
        # since some of our axes are flipped.
        self.axisSignMapper = {0: -1, 1: 1, 2: 1}
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
                self.softlimits = [[4000, 25000],
                                   [4000, 25000],
                                   [7300, 25000]]
                self.safeties = [[4000, 25000],
                                   [4000, 25000],
                                   [7300, 25000]]
#            events.subscribe('user logout', self.onLogout)
            events.subscribe('user abort', self.onAbort)
            events.subscribe('macro stage xy draw', self.onMacroStagePaint)
            events.subscribe('cockpit initialization complete',
                    self.promptExerciseStage)

        

    def initialize(self):
        print "in init"
        self.connection = util.connection.Connection(
                'nano', self.ipAddress, self.port)
        self.connection.connect(self.receiveData)
        self.connection.connection.startOMX()
        self.curPosition[:] = self.connection.connection.posXYZ_OMX()
        print self.curPosition
#        for axis, (minVal, maxVal) in enumerate(self.safeties):
#            try:
#                self.connection.connection.setSafetyMinOMX(axis, minVal)
#            except Exception, e:
#                newTarget = int(self.curPosition[axis]) - 1
#                wx.MessageDialog(None,
#                        ("The %s axis " % ['X', 'Y', 'Z'][axis]) +
#                        ("is below the default safety min of %.2f, " % minVal) #+
#                        ("so the safety min is being set to %d" % newTarget),
#                        style = wx.ICON_EXCLAMATION | wx.OK).ShowModal()
#                self.connection.connection.setSafetyMinOMX(axis, newTarget)
#                self.safeties[axis][0] = newTarget
#            try:
#                self.connection.connection.setSafetyMaxOMX(axis, maxVal)
#            except Exception, e:
#                newTarget = int(self.curPosition[axis]) + 1
#                wx.MessageDialog(None,
#                        ("The %s axis " % ['X', 'Y', 'Z'][axis]) +
#                        ("is below the default safety min of %.2f, " % minVal) #+
#                        ("so the safety min is being set to %d" % newTarget),
#                        style = wx.ICON_EXCLAMATION | wx.OK).ShowModal()
#                self.connection.connection.setSafetyMaxOMX(axis, newTarget)
#                self.safeties[axis][1] = newTarget

        # Set the field diaphragm to fully open.
        # Angles for the various diaphragm positions are 45 degrees apart,
        # with a 3-degree offset. NB we assume that the user will never
        # want anything but a fully-open diaphragm because we have the
        # fiber mode selector which accomplishes the same purpose, but better.
#        self.connection.connection.fd_move(93, 4)


    # ## Generate the fiber mode selector control.
    # def makeUI(self, parent):
    #     sizer = wx.BoxSizer(wx.VERTICAL)
    #     label = wx.StaticText(parent, -1, "Fiber mode:")
    #     label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
    #     sizer.Add(label)
    #     for mode in ['Full field', 'Spotlight']:
    #         button = gui.toggleButton.ToggleButton(
    #                 textSize = 12, label = mode, size = (100, 50),
    #                 parent = parent)
    #         button.Bind(wx.EVT_LEFT_DOWN,
    #                 lambda event, mode = mode: self.setFiberMode(mode))
    #         sizer.Add(button)
    #         self.fiberModeButtons.append(button)
    #     return sizer


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
            initialPos = tuple(self.xyPositionCache)
#            interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            for i in xrange(5):
                print "Rep %d of 5..." % i
                for position in self.softlimits:
                    interfaces.stageMover.goToXY(position, shouldBlock = True)
            interfaces.stageMover.goToXY((0, 0), shouldBlock = True)
            interfaces.stageMover.goToXY(initialPos, shouldBlock = True)
            print "Exercising complete. Thank you!"
            
            util.userConfig.setValue('NanomoverLastExerciseTimestamp',
                    time.time(), isGlobal = True)



    def performSubscriptions(self):
#        events.subscribe('IR remote start', self.onRemoteStart)
#        events.subscribe('IR remote stop', self.onAbort)
        events.subscribe('user abort', self.onAbort)


    def makeInitialPublications(self):
        events.publish('new status light', 'stage vertical position', '')
        self.publishPosition()
#        self.setFiberMode('Full field')

    ## The XY Macro Stage view is painting itself; draw the banned
    # rectangles as pink excluded zones.
    def onMacroStagePaint(self, stage):
        glColor3f(1, .6, .6)
        glBegin(GL_QUADS)
        for (x1, y1), (x2, y2) in BANNED_RECTANGLES:
            stage.scaledVertex(x1, y1)
            stage.scaledVertex(x1, y2)
            stage.scaledVertex(x2, y2)
            stage.scaledVertex(x2, y1)
        glEnd()


    def getHandlers(self):
        result = []
        for axis in xrange(3):
            stepSizes = [.1, .2, .5, 1, 2, 5, 10, 50, 100, 500, 1000]
            if axis == 2:
                # Add smaller step sizes for the Z axis.
                stepSizes = [.01, .02, .05] + stepSizes
            lowLimit, highLimit = self.safeties[axis]
            result.append(handlers.stagePositioner.PositionerHandler(
                "%d nanomover" % axis, "%d stage motion" % axis, False, 
                {'moveAbsolute': self.moveAbsolute, 
                    'moveRelative': self.moveRelative,
                    'getPosition': self.getPosition,
                    'setSafety': self.setSafety}, 
                axis, stepSizes, 3, 
                (4000, 25000), (lowLimit, highLimit)))
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


    # ## Set the fiber mode. We can switch between a fiber that fully illuminates
    # # the sample, and one that focuses light on a small area.
    # def setFiberMode(self, mode):
    #     index = int(mode == 'Full field')
    #     self.moveFiberCoffin(coffinPositions[index])
    #     self.moveFiberCrypt(cryptPositions[index])
    #     for button in self.fiberModeButtons:
    #         button.setActive(button.GetLabel() == mode)


    # ## Move the fiber motor in the coffin (optical table with all the lasers).
    # def moveFiberCoffin(self, position):
    #     delta = abs(position - self.connection.connection.fiberSelector_pos())
    #     if delta > MIN_FIBER_MOTION_DELTA:
    #         self.connection.connection.fiberSelector_move(position, 2.5)

            
    # ## Move the fiber motor in the crypt (closet with the objective and sample)
    # def moveFiberCrypt(self, position):
    #     delta = abs(position - self.connection.connection.vp_getPosStatus()[0])
    #     if delta > MIN_FIBER_MOTION_DELTA:
    #         self.connection.connection.vp_move(position, 20)


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
        self.connection.connection.moveOMX_axis(axis, pos)


    ## Move a specific axis by a given amount.
    def moveRelative(self, axis, delta):
        self.connection.connection.moveOMX_dAxis(axis, delta)


    ## Get the position along the given axis.
    def getPosition(self, axis):
        return self.curPosition[axis]


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


    ## User is interacting with the remote; start motion in the specified
    # direction.
    # \param direction -1 for negative, +1 for positive.
#    def onRemoteStart(self, axis, direction):
#        self.moveAbsolute(axis, self.safeties[axis][direction > 0])
