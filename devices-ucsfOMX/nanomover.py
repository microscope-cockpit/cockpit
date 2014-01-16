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

CLASS_NAME = 'NanomoverDevice'


## Positions for the coffin fiber positioner for full field and spotlight
# modes, respectively.
coffinPositions = [16.5, 5.38]
## Positions for the crypt fiber positioner, same.
cryptPositions = [11.505, .210]
## Minimum movement distance; if we're within this much of the target then
# we don't bother moving.
MIN_FIBER_MOTION_DELTA = .001


class NanomoverDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## Current stage position information.
        self.curPosition = [14500, 14500, 14500]
        ## IP address and port of the Nanomover controller program.
        self.ipAddress = '192.168.12.50'
        self.port = 7766
        ## Connection to the Nanomover controller program.
        self.connection = None
        ## Soft safety motion limits. 
        self.safeties = [[4000, 25000], [4000, 25000], [7300, 25000]]
        ## List of ToggleButton instances for the fiber selector.
        self.fiberModeButtons = []


    def initialize(self):
        self.connection = util.connection.Connection(
                'nano', self.ipAddress, self.port)
        self.connection.connect(self.receiveData)
        self.curPosition[:] = self.connection.connection.posXYZ_OMX()
        for axis, (minVal, maxVal) in enumerate(self.safeties):
            try:
                self.connection.connection.setSafetyMinOMX(axis, minVal)
            except Exception, e:
                newTarget = int(self.curPosition[axis]) - 1
                wx.MessageDialog(None,
                        ("The %s axis " % ['X', 'Y', 'Z'][axis]) +
                        ("is below the default safety min of %.2f, " % minVal) +
                        ("so the safety min is being set to %d" % newTarget),
                        style = wx.ICON_EXCLAMATION | wx.OK).ShowModal()
                self.connection.connection.setSafetyMinOMX(axis, newTarget)
                self.safeties[axis][0] = newTarget
            try:
                self.connection.connection.setSafetyMaxOMX(axis, maxVal)
            except Exception, e:
                newTarget = int(self.curPosition[axis]) + 1
                wx.MessageDialog(None,
                        ("The %s axis " % ['X', 'Y', 'Z'][axis]) +
                        ("is below the default safety min of %.2f, " % minVal) +
                        ("so the safety min is being set to %d" % newTarget),
                        style = wx.ICON_EXCLAMATION | wx.OK).ShowModal()
                self.connection.connection.setSafetyMaxOMX(axis, newTarget)
                self.safeties[axis][1] = newTarget

        # Set the field diaphragm to fully open.
        # Angles for the various diaphragm positions are 45 degrees apart,
        # with a 3-degree offset. NB we assume that the user will never
        # want anything but a fully-open diaphragm because we have the
        # fiber mode selector which accomplishes the same purpose, but better.
        self.connection.connection.fd_move(93, 4)


    ## Generate the fiber mode selector control.
    def makeUI(self, parent):
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(parent, -1, "Fiber mode:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        for mode in ['Full field', 'Spotlight']:
            button = gui.toggleButton.ToggleButton(
                    textSize = 12, label = mode, size = (100, 50),
                    parent = parent)
            button.Bind(wx.EVT_LEFT_DOWN,
                    lambda event, mode = mode: self.setFiberMode(mode))
            sizer.Add(button)
            self.fiberModeButtons.append(button)
        return sizer


    def performSubscriptions(self):
        events.subscribe('IR remote start', self.onRemoteStart)
        events.subscribe('IR remote stop', self.onAbort)
        events.subscribe('user abort', self.onAbort)


    def makeInitialPublications(self):
        events.publish('new status light', 'stage vertical position', '')
        self.publishPosition()
        self.setFiberMode('Full field')


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


    ## Set the fiber mode. We can switch between a fiber that fully illuminates
    # the sample, and one that focuses light on a small area.
    def setFiberMode(self, mode):
        index = int(mode == 'Full field')
        self.moveFiberCoffin(coffinPositions[index])
        self.moveFiberCrypt(cryptPositions[index])
        for button in self.fiberModeButtons:
            button.setActive(button.GetLabel() == mode)


    ## Move the fiber motor in the coffin (optical table with all the lasers).
    def moveFiberCoffin(self, position):
        delta = abs(position - self.connection.connection.fiberSelector_pos())
        if delta > MIN_FIBER_MOTION_DELTA:
            self.connection.connection.fiberSelector_move(position, 2.5)

            
    ## Move the fiber motor in the crypt (closet with the objective and sample)
    def moveFiberCrypt(self, position):
        delta = abs(position - self.connection.connection.vp_getPosStatus()[0])
        if delta > MIN_FIBER_MOTION_DELTA:
            self.connection.connection.vp_move(position, 20)


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
    def onRemoteStart(self, axis, direction):
        self.moveAbsolute(axis, self.safeties[axis][direction > 0])
