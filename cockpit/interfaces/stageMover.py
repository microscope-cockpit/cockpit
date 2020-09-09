#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 Nicholas Hall <nicholas.hall@dtc.ox.ac.uk>
## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.

import math
import operator
import typing

from cockpit import depot
from cockpit import events
from cockpit.util import userConfig

import numpy
import threading
import wx


AxisLimits = typing.Tuple[float, float]
StageLimits = typing.Tuple[AxisLimits, AxisLimits, AxisLimits]


## Stage movement threshold (previously a hard-coded value).
# There can be problems when this doesn't match a corresponding threshold
# the stage device code.
#TODO:  This should be defined in only one place, either here,
# in the stage code, or in a config file.
STAGE_MIN_MOVEMENT = 0.3
# Map possible axis identifiers to canonical integer identifiers.
AXIS_MAP = {}
AXIS_MAP.update({k:0 for k in '0xX'})
AXIS_MAP.update({k:1 for k in '1yY'})
AXIS_MAP.update({k:2 for k in '2zZ'})
AXIS_MAP.update({k:k for k in [0,1,2]})

## This module handles general stage motion: "go to this position", "move by
# this delta", "remember this position", "go to this remembered position",
# etc. The cockpit deals with this module instead of speaking direction to
# StagePositionerHandlers.
# Several of the functions in this module accept an "axis" parameter. The
# mapping is 0: X; 1: Y; 2: Z.

## Auto-incrementing unique value to mark each Site instance.
uniqueSiteIndex = 0


## A Site is a simple container class that represents a saved location
# on the stage.
class Site:
    ## \param position 3D location (Numpy vector) of the Site.
    # \param group String describing the group the Site belongs to.
    # \param color RGB tuple used to color the Site in the UI.
    # \param size Size (in arbitrary units) to draw the site.
    def __init__(self, position, group = None, color = (0, 255, 0),
            size = 25):
        self.position = position
        self.group = group
        self.color = color
        self.size = size
        global uniqueSiteIndex
        uniqueSiteIndex += 1
        ## Unique ID for the Site.
        self.uniqueID = uniqueSiteIndex


    ## Serialize the site -- convert it to a string we can use to
    # reconstruct it later.
    def serialize(self):
        result = ''
        result += ','.join(map(str, self.position))
        result += ',%s,' % self.group
        result += ','.join(map(str, self.color))
        result += ',%.2f,%d' % (self.size, self.uniqueID)
        return result


## Generate a new Site from a text string generated from serialize(),
# above.
def deserializeSite(line):
    x, y, z, group, r, g, b, size, id = line.split(',')
    x, y, z, r, g, b, size = map(float, (x, y, z, r, g, b, size))
    id = int(id)
    if group == 'None':
        group = None
        # Otherwise let group remain as a string.
    result = Site(numpy.array((x, y, z)), group, (r, g, b), size)
    result.uniqueID = id
    return result


def _SensibleStepSize(step_size: float, bases: typing.Sequence[int],
                      cmp: typing.Callable[[float, float], bool]) -> float:
    power_of_ten = 10**math.floor(math.log10(step_size))
    for base in bases:
        threshold = base * power_of_ten
        if cmp(step_size, threshold):
            return threshold
    else:
        raise RuntimeError('failed to estimate best step size after trying'
                           ' all bases in %s' % bases)

def SensibleNextStepSize(step_size: float) -> float:
    return _SensibleStepSize(step_size, [2, 5, 10], operator.lt)

def SensiblePreviousStepSize(step_size: float) -> float:
    return _SensibleStepSize(step_size, [5, 2, 1, 0.5], operator.gt)


## This class provides an interface between the rest of the UI and the Devices
# that handle moving the stage.
class StageMover:
    def __init__(self):
        ## Maps axis to the handlers for that axis, sorted by their range of
        # motion.
        self.axisToHandlers = depot.getSortedStageMovers()
        if set(self.axisToHandlers.keys()) != {0, 1, 2}:
            raise ValueError('stage mover requires 3 axis: X, Y, and Z')

        # FIXME: we should have sensible defaults (see issue #638).
        self._saved_top = userConfig.getValue('savedTop', default=3010.0)
        self._saved_bottom = userConfig.getValue('savedBottom', default=3000.0)

        ## XXX: We have a single index for all axis, even though each
        ## axis may have a different number of stages.  While we don't
        ## refactor this assumption, we just make copies of the movers
        ## with the most precise movement (issues #413 and #415)
        self.n_stages = max([len(s) for s in self.axisToHandlers.values()])
        for axis, stages in self.axisToHandlers.items():
            stages.extend([stages[-1]] * (self.n_stages - len(stages)))

        ## Indicates which stage handler is currently under control.
        self.curHandlerIndex = 0
        ## Maps Site unique IDs to Site instances.
        self.idToSite = {}

        # Compute the hard motion limits for each axis as the
        # summation of all limits for handlers on that axis.
        hard_limits = [None] * 3
        for axis in range(3):
            lower = 0.0
            upper = 0.0
            # We need set() to avoid duplicated handlers, and we might
            # have duplicated handlers because of the hack to meet
            # cockpit requirements that all axis have the same number
            # of handlers (see comments on issue #413).
            for handler in set(self.axisToHandlers[axis]):
                handler_limits = handler.getHardLimits()
                lower += handler_limits[0]
                upper += handler_limits[1]
            hard_limits[axis] = (lower, upper)
        # Use a tuple to prevent changes to it, and assemble it like
        # this to enable static code analysis.
        self._hard_limits = (hard_limits[0], hard_limits[1], hard_limits[2])

        # Compute the initial step sizes.  We have different step
        # sizes for each handler index which maybe doesn't make sense
        # anymore but comes from the time when it were the handlers
        # themselves that kept track of step size.
        self._step_sizes = [] # type: typing.List[typing.Tuple[float, float, float]]
        for stage_index in range(self.n_stages):
            default_step_sizes = []
            for axis in (0, 1, 2):
                limits = self.axisToHandlers[axis][stage_index].getHardLimits()
                step_size = SensiblePreviousStepSize((limits[1] - limits[0])
                                                     / 100.0)
                default_step_sizes.append(step_size)
            # Default is 1/100 of the axis length but in rectangular
            # stages that will lead to xy with different step sizes so
            # use the min of the two.
            min_xy = min(default_step_sizes[0], default_step_sizes[1])
            self._step_sizes.append((min_xy, min_xy, default_step_sizes[2]))

        ## Maps handler names to events indicating if those handlers
        # have stopped moving.
        self.nameToStoppedEvent = {}
        events.subscribe(events.STAGE_MOVER, self.onMotion)
        events.subscribe(events.STAGE_STOPPED, self.onStop)


    @property
    def SavedTop(self) -> float:
        return self._saved_top

    @SavedTop.setter
    def SavedTop(self, pos: float) -> None:
        userConfig.setValue('savedTop', pos)
        self._saved_top = pos
        events.publish(events.STAGE_TOP_BOTTOM)

    @property
    def SavedBottom(self) -> float:
        return self._saved_bottom

    @SavedBottom.setter
    def SavedBottom(self, pos: float) -> None:
        userConfig.setValue('savedBottom', pos)
        self._saved_bottom = pos
        events.publish(events.STAGE_TOP_BOTTOM)


    def GetStepSizes(self) -> typing.Tuple[float, float, float]:
        """Return a (dX, dY, dZ) tuple of the current step sizes."""
        return self._step_sizes[self.curHandlerIndex]

    def Step(self, direction: typing.Tuple[int, int, int]) -> None:
        """Move one step with the current active handler in the specified
        direction(s).

        Args:
            direction: A tuple/list of length equal to the number of
                axes of motion, where each element is the number of
                steps (positive or negative) to take along that axis.
        """
        if len(direction) != 3:
            raise ValueError('direction must be a 3 element list')
        for axis, sign in enumerate(direction):
            if sign != 0:
                step_size = self._step_sizes[self.curHandlerIndex][axis]
                handler = self.axisToHandlers[axis][self.curHandlerIndex]
                handler.moveRelative(step_size * sign)

    def SetStepSize(self, axis: int, step_size: float) -> None:
        if step_size <= 0.0:
            raise ValueError('step size must be a positive number')
        elif axis not in [0, 1, 2]:
            raise ValueError('axis must be in [0, 1, 2]')
        step_sizes = list(self.GetStepSizes())
        step_sizes[axis] = step_size
        self._step_sizes[self.curHandlerIndex] = tuple(step_sizes)
        events.publish('stage step size', axis, step_size)

    def ChangeStepSize(self, direction: int) -> None:
        if direction == +1:
            guess_new = SensibleNextStepSize
        elif direction == -1:
            guess_new = SensiblePreviousStepSize
        else:
            raise ValueError('direction must be -1 (decrease) or +1 (increase)')
        old_step_sizes = self.GetStepSizes()
        new_step_sizes = tuple([guess_new(x) for x in old_step_sizes])
        self._step_sizes[self.curHandlerIndex] = new_step_sizes

        for axis, step_size in enumerate(self.GetStepSizes()):
            events.publish('stage step size', axis, step_size)


    ## Handle one of our devices moving. We just republish an abstracted
    # stage position for that axis.
    def onMotion(self, axis):
        events.publish(events.STAGE_POSITION, axis, getPositionForAxis(axis))


    ## Handle one of our devices stopping motion; this unblocks _goToAxes
    # if it is waiting.
    def onStop(self, name):
        if name in self.nameToStoppedEvent:
            self.nameToStoppedEvent[name].set()


    ## Internal function to go to the specified location (specified as a list
    # of (axis, position) tuples). Wait for the axes to stop moving, if
    # shouldBlock is true.
    # \todo Assumes that the target position is within the range of motion of
    # the current handler.
    def _goToAxes(self, position, shouldBlock = False):
        waiters = []
        for axis, target in position:
            # Get the offset for the movers that aren't being adjusted.
            offset = 0
            for handler in self.axisToHandlers[axis]:
                if handler != self.axisToHandlers[axis][self.curHandlerIndex]:
                    offset += handler.getPosition()

            handler = self.axisToHandlers[axis][self.curHandlerIndex]
            # Check if we need to bother moving.
            if abs(handler.getPosition() - (target - offset)) > STAGE_MIN_MOVEMENT:
                event = threading.Event()
                waiters.append(event)
                self.nameToStoppedEvent[handler.name] = event
                handler.moveAbsolute(target - offset)
        if shouldBlock:
            for event in waiters:
                try:
                    event.wait(30)
                except Exception as e:
                    print ("Failed waiting for stage to stop after 30s")



## Global singleton.
mover = None


## Create the StageMover.
def initialize():
    global mover
    mover = StageMover()


## Publicize any information that various widgets care about.
def makeInitialPublications():
    #for axis in range(3):
    for axis in mover.axisToHandlers.keys():
        events.publish(events.STAGE_POSITION, axis, getPositionForAxis(axis))
        limits = getSoftLimitsForAxis(axis)
        for isMax in [0, 1]:
            events.publish("soft safety limit", axis, limits[isMax],
                    bool(isMax))


## Various module-global functions for interacting with the objects in the
# Mover.

def step(direction):
    mover.Step(direction)


## Change to the next handler.
def changeMover():
    oldIndex = mover.curHandlerIndex
    newIndex = (mover.curHandlerIndex + 1) % mover.n_stages
    if newIndex != oldIndex:
        old_step_sizes = mover.GetStepSizes()
        mover.curHandlerIndex = newIndex
        events.publish("stage step index", mover.curHandlerIndex)
        for axis, new_step_size in enumerate(mover.GetStepSizes()):
            if old_step_sizes[axis] != new_step_size:
                events.publish("stage step size", axis, new_step_size)


## Change the step size for the current handlers.
def changeStepSize(direction):
    mover.ChangeStepSize(direction)


## Recenter the fine-motion devices by adjusting the large-scale motion
# device.
def recenterFineMotion():
    for axis, handlers in mover.axisToHandlers.items():
        if len(set(handlers)) < 2:
            continue # Only makes sense if one has at least two stages

        totalDelta = 0
        for handler in handlers[1:]:
            # Assume that the fine-motion devices want to be in the center
            # of their ranges.
            curPosition = handler.getPosition()
            safeties = handler.getHardLimits()
            target = (safeties[1] - safeties[0]) / 2 + safeties[0]
            handler.moveAbsolute(target)
            totalDelta += target - curPosition
        handlers[0].moveRelative(-totalDelta)


## Move to the specified position using the current handler.
def goTo(position, shouldBlock = False):
    if len(position) != len(mover.axisToHandlers.keys()):
        raise RuntimeError("Asked to go to position with wrong number of axes (%d != %d)" % (len(position), len(mover.axisToHandlers.keys())))
    mover._goToAxes(enumerate(position), shouldBlock)


## As goTo, but only in X and Y.
def goToXY(position, shouldBlock = False):
    if len(position) != 2:
        raise RuntimeError("Asked to go to XY position with wrong number of axes (%d != %d)" % (len(position), 2))
    mover._goToAxes(enumerate(position), shouldBlock)


## As goTo, but only in Z.
def goToZ(position, shouldBlock = False):
    mover._goToAxes([(2, position)], shouldBlock)


## Move by the specified 3D offset.
def moveRelative(offset, shouldBlock = False):
    numAxes = len(mover.axisToHandlers.keys())
    if len(offset) != numAxes:
        raise RuntimeError("Asked to move relatively with wrong number of axes (%d != %d)" % (len(offset), numAxes))
    curPosition = getPosition()
    vals = [offset[i] + curPosition[i] for i in range(numAxes)]
    goTo(vals, shouldBlock)


## Wait for any stage motion to cease.
def waitForStop(timeout = 5):
    for name, event in mover.nameToStoppedEvent.items():
        if not event.wait(timeout):
            raise RuntimeError("Timed out waiting for %s to stop" % name)


## Move to the specified site.
def goToSite(uniqueID, shouldBlock = False):
    site = mover.idToSite[uniqueID]
    objOffset = wx.GetApp().Objectives.GetOffset()
    offsetPosition=list(site.position)
    for i in range(len(offsetPosition)):
        offsetPosition[i]=offsetPosition[i]+objOffset[i]
    goTo(offsetPosition, shouldBlock)


## Get a Site with a given ID.
def getSite(uniqueID):
    return mover.idToSite[uniqueID]


## Save a new Site. Use default settings if none is provided.
def saveSite(newSite = None):
    if newSite is None:
        newSite = Site(getPosition())
    mover.idToSite[newSite.uniqueID] = newSite
    # Start counting from the new site, if necessary.
    global uniqueSiteIndex
    uniqueSiteIndex = max(uniqueSiteIndex, newSite.uniqueID)
    events.publish('new site', newSite)


## Remove a site with the specified ID.
def deleteSite(siteID):
    site = mover.idToSite[siteID]
    del mover.idToSite[siteID]
    events.publish('site deleted', site)
    # HACK: if this siteID is for the most-recently created
    # site, decrement the global site ID.
    global uniqueSiteIndex
    if siteID == uniqueSiteIndex:
        uniqueSiteIndex -= 1


## Retrieve the sites as a list.
def getAllSites() -> typing.List[int]:
    return list(mover.idToSite.values())


## Return True if there's a site with the specified ID.
def doesSiteExist(siteId):
    return siteId in mover.idToSite


## Return True iff the position of the specified site is inside of all of our
# soft motion limits.
def canReachSite(siteId):
    position = mover.idToSite[siteId].position
    safeties = getSoftLimits()
    for axis, pos in enumerate(position):
        if safeties[axis][0] > pos or pos > safeties[axis][1]:
            return False
    return True


## Record sites to a file.
def writeSitesToFile(filename):
    with open(filename, 'w') as handle:
        for id, site in mover.idToSite.items():
            handle.write(site.serialize() + '\n')


## Load sites from a file.
def loadSites(filename):
    with open(filename, 'r') as handle:
        for line in handle:
            site = deserializeSite(line)
            saveSite(site)


## Return the exact stage position, as the aggregate of all handlers'
# positions.
def getPosition():
    result = 3 * [0]
    for axis, handlers in mover.axisToHandlers.items():
        for handler in set(handlers):
            result[axis] += handler.getPosition()
    return result


## Return the exact stage position for the given axis.
def getPositionForAxis(axis):
    result = 0
    for handler in set(mover.axisToHandlers[axis]):
        result += handler.getPosition()
    return result


## Return a list of (X, Y, Z) tuples indicating the positions for all
# handlers we have. If there's an axis with more handlers than the others,
# then those axes will have None instead of a position towards the
# end of the list.
def getAllPositions():
    result = []
    for i in range(mover.n_stages):
        current = [None] * len(mover.axisToHandlers)
        for axis, handlers in mover.axisToHandlers.items():
            current[axis] = handlers[i].getPosition()
        result.append(tuple(current))
    return result


def getCurStepSizes():
    return mover.GetStepSizes()


## Simple getter.
def getCurHandlerIndex():
    return mover.curHandlerIndex


## Get the hard motion limits for a specific axis, as the summation of all
# limits for movers on that axis.
def getHardLimitsForAxis(axis: int) -> AxisLimits:
    return mover._hard_limits[axis]


## Repeat the above for each axis.
def getHardLimits() -> StageLimits:
    return mover._hard_limits


## Returns a list of all hard motion limits for the given axis.
def getIndividualHardLimits(axis):
    return [handler.getHardLimits() for handler in mover.axisToHandlers[axis]]


## Get the soft motion limits for a specific axis, as the summation of all
# limits for movers on that axis.
def getSoftLimitsForAxis(axis):
    lowLimit = 0
    highLimit = 0
    for handler in set(mover.axisToHandlers[axis]):
        low, high = handler.getSoftLimits()
        lowLimit += low
        highLimit += high
    return (lowLimit, highLimit)


## Repeat the above for each axis.
def getSoftLimits():
    result = []
    for axis in sorted(mover.axisToHandlers.keys()):
        result.append(getSoftLimitsForAxis(axis))
    return result


## Returns a list of all soft motion limits for the given axis.
def getIndividualSoftLimits(axis):
    return [handler.getSoftLimits() for handler in mover.axisToHandlers[axis]]


## Try to change the software safety limits. Return True if we succeed,
# False otherwise.
def setSoftLimit(axis, value, isMax):
    # \todo For now we assume that only the first handler, with the greatest
    # range of motion, cares about soft limits.
    try:
        mover.axisToHandlers[axis][0].setSoftLimit(value, isMax)
        events.publish("soft safety limit", axis, value, isMax)
        return True
    except Exception as e:
        # \todo Assuming that any exception here means the safety was not
        # set.
        return False


def setSoftMin(axis, value):
    setSoftLimit(axis, value, False)


def setSoftMax(axis, value):
    setSoftLimit(axis, value, True)


def moveZCheckMoverLimits(target):
    # Use the nanomover (and, optionally, also the stage piezo) to
    # move to the target elevation.

    # Need to check current mover limits, see if we exceed them and if
    # so drop down to lower mover handler.
    originalMover = mover.curHandlerIndex
    limits = getIndividualSoftLimits(2)
    offset = target - getPosition()[2]


    # FIXME: IMD 2018-11-07 I think this test needs to be currentpos
    # of the current mover not the overall pos.
    while mover.curHandlerIndex >= 0:
        handler = mover.curHandlerIndex
        moverPos = getAllPositions()[handler][2]
        if ((moverPos + offset) > limits[mover.curHandlerIndex][1]
            or (moverPos + offset) < limits[mover.curHandlerIndex][0]):
            # need to drop down a handler to see if next handler can do the move
            mover.curHandlerIndex -= 1
            if mover.curHandlerIndex < 0:
                print ("Move too large for any Z mover.")

        else:
            goToZ(target)
            break

    # return to original active mover.
    mover.curHandlerIndex = originalMover


## Use the nearest-neighbor algorithm to select the order in which to
# visit the selected sites (i.e. try to solve the Traveling Salesman problem).
# This could, theoretically, behave worse than just taking the list in
# its default order, so we do check the default list's travel time and
# use it if it's superior, on the assumption that users will typically
# select sites in some basically sane order.
# \param baseOrder List of site IDs.
def optimisedSiteOrder(baseOrder):
    if len(baseOrder) == 0:
        return []
    markedPoints = set()
    pointsInOrder = []
    totalTourCost = 0
    curPoint = baseOrder[0]
    remainingPoints = set(baseOrder)

    # Calculate the travel time between two sites. Since we move
    # simultaneously in each axis, this is simply the maximum
    # distance along any given axis.
    def distance(a, b):
        p1 = mover.idToSite[a].position
        p2 = mover.idToSite[b].position
        return max([abs(a - b) for a, b in zip(p1, p2)])

    while remainingPoints:
        markedPoints.add(curPoint)
        pointsInOrder.append(curPoint)
        remainingPoints.remove(curPoint)
        if not remainingPoints:
            break

        # Find the closest remaining point
        nextPoint = min(remainingPoints, key = lambda a: distance(a, curPoint))
        totalTourCost += distance(curPoint, nextPoint)
        curPoint = nextPoint
    # Add cost of closing the loop back to the first point.
    totalTourCost += distance(baseOrder[0], curPoint)

    # Calculate the cost of just doing everything in order.
    simpleTourCost = 0
    for i in range(len(baseOrder)):
        simpleTourCost += distance(baseOrder[i], baseOrder[(i + 1) % len(baseOrder)])
    simpleTourCost += distance(baseOrder[0], baseOrder[-1])

    if simpleTourCost < totalTourCost:
        # Nearest-neighbor is worse than just going in the
        # user-specified order
        return baseOrder.copy()
    return pointsInOrder
