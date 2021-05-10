#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 Frederik Lange <frederik.lange@dtc.ox.ac.uk>
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

import collections
import math
import threading
import time

import numpy
import scipy.ndimage.measurements
import wx
from OpenGL.GL import *

import cockpit.gui
import cockpit.gui.camera.window
import cockpit.gui.dialogs.getNumberDialog
import cockpit.gui.dialogs.gridSitesDialog
import cockpit.gui.dialogs.offsetSitesDialog
import cockpit.gui.freetype
import cockpit.gui.guiUtils
import cockpit.gui.keyboard
import cockpit.interfaces
import cockpit.interfaces.stageMover
import cockpit.util.files
import cockpit.util.userConfig
from cockpit import depot
from cockpit import events
from cockpit.gui.mosaic import canvas
from cockpit.gui.primitive import Primitive


## Valid colors to use for site markers.
SITE_COLORS = [('green', (0, 1, 0)), ('red', (1, 0, 0)),
    ('blue', (0, 0, 1)), ('orange', (1, .6, 0))]

## Timeout for mosaic new image events
CAMERA_TIMEOUT = 1

## Simple structure for marking potential beads.
BeadSite = collections.namedtuple('BeadSite', ['pos', 'size', 'intensity'])

from functools import wraps


def _pauseMosaicLoop(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        is_running = self.shouldContinue.is_set()
        if not is_running:
            return func(self, *args, **kwargs)
        else:
            self.shouldContinue.clear()
            try:
                return func(self, *args, **kwargs)
            finally:
                self.shouldContinue.set()
    return wrapped


class MosaicCommon:
    # A class to house methods that are common to both the Mosaic
    # and TouchScreen windows. Previously, these were dynamically
    # rebound on the TouchScreen window, which worked fine in
    # python 3, but threw TypeErrors in python 2.
    # TODO: refactor to eliminate this class; see notes on each method.

    ## Go to the specified XY position. If we have a focus plane defined,
    # go to the appropriate Z position to maintain focus.
    # Refactoring: If the stageMover dealt with the focal plane params and mover
    # switching, this method could probably be eliminated.
    def goTo(self, target, shouldBlock=False):
        if self.focalPlaneParams:
            targetZ = self.getFocusZ(target)
            cockpit.interfaces.stageMover.goTo((target[0], target[1], targetZ),
                                               shouldBlock)
        else:
            # IMD 20150306 Save current mover, change to coarse to generate mosaic
            # do move, and change mover back.
            originalMover = cockpit.interfaces.stageMover.mover.curHandlerIndex
            cockpit.interfaces.stageMover.mover.curHandlerIndex = 0
            cockpit.interfaces.stageMover.goToXY(target, shouldBlock)
            cockpit.interfaces.stageMover.mover.curHandlerIndex = originalMover


    ## Draw the overlay. This largely consists of a crosshairs indicating
    # the current stage position, and any sites the user has saved.
    # Refactoring: this could probably move to the Canvas class by eliminating
    # references to data on the MosaicWindow as follows:
    #   roll self.scalebar and self.drawCrosshairs into this method;
    #   put self.scalefont onto the canvas;
    #   pull self.offset straight from the objective;
    #   move self.selectedSites to the stageMover or some other space manager;
    def drawOverlay(self):
        siteLineWidth = max(1, self.canvas.scale * 1.5)
        siteFontScale = 3 / max(5.0, self.canvas.scale)
        for site in cockpit.interfaces.stageMover.getAllSites():
            # Draw a crude circle.
            x, y = site.position[:2]
            x = -x
            glLineWidth(siteLineWidth)
            glColor3f(*site.color)
            glBegin(GL_LINE_LOOP)
            for i in range(8):
                glVertex3f(x + site.size * numpy.cos(numpy.pi * i / 4.0),
                        y + site.size * numpy.sin(numpy.pi * i / 4.0), 0)
            glEnd()
            glLineWidth(1)

            glPushMatrix()
            glTranslatef(x, y, 0)
            glScalef(siteFontScale, siteFontScale, 1)
            self.site_face.render(str(site.uniqueID))
            glPopMatrix()

        self.drawCrosshairs(cockpit.interfaces.stageMover.getPosition()[:2], (1, 0, 0),
                            offset=True)

        # If we're selecting tiles, draw the box the user is selecting.
        if self.selectTilesFunc is not None and self.lastClickPos is not None:
            start = self.canvas.mapScreenToCanvas(self.lastClickPos)
            end = self.canvas.mapScreenToCanvas(self.prevMousePos)
            glColor3f(0, 0, 1)
            glBegin(GL_LINE_LOOP)
            glVertex2f(-start[0], start[1])
            glVertex2f(-start[0], end[1])
            glVertex2f(-end[0], end[1])
            glVertex2f(-end[0], start[1])
            glEnd()

        # Highlight selected sites with crosshairs.
        for site in self.selectedSites:
            self.drawCrosshairs(site.position[:2], (0, 0, 1), 10000,
                                offset=False)

        # Draw the soft and hard stage motion limits
        glEnable(GL_LINE_STIPPLE)
        glLineWidth(2)
        softSafeties = cockpit.interfaces.stageMover.getSoftLimits()[:2]
        hardSafeties = cockpit.interfaces.stageMover.getHardLimits()[:2]
        for safeties, color, stipple in [(softSafeties, (0, 1, 0), 0x5555),
                                         (hardSafeties, (0, 0, 1), 0xAAAA)]:
            x1, x2 = safeties[0]
            y1, y2 = safeties[1]
            if hasattr (self, 'offset'):
                #once again consistancy of offset calculations.
                x1 -=  self.offset[0]
                x2 -=  self.offset[0]
                y1 -=  self.offset[1]
                y2 -=  self.offset[1]
            glLineStipple(3, stipple)
            glColor3f(*color)
            glBegin(GL_LINE_LOOP)
            glVertex2f(-x1, y1)
            glVertex2f(-x2, y1)
            glVertex2f(-x2, y2)
            glVertex2f(-x1, y2)
            glEnd()
        glLineWidth(1)
        glDisable(GL_LINE_STIPPLE)

        #Draw a scale bar if the scalebar size is not zero.
        if (self.scalebar != 0):
            # Scale bar width.
            self.scalebar = 100*(10**math.floor(math.log(1/self.canvas.scale,10)))
            # Scale bar position, near the top left-hand corner.
            scaleFactor = self.GetContentScaleFactor()
            scalebarPos = [30*scaleFactor,-10*scaleFactor]

            # Scale bar vertices.
            x1 = scalebarPos[0]/self.canvas.scale
            x2 = (scalebarPos[0]+self.scalebar*self.canvas.scale)/self.canvas.scale
            y1 = scalebarPos[1]/self.canvas.scale
            canvasPos=self.canvas.mapScreenToCanvas((0,0))
            x1 -= canvasPos[0]
            x2 -= canvasPos[0]
            y1 += canvasPos[1]


            # Do the actual drawing
            glColor3f(255, 0, 0)
            # The scale bar itself.
            glLineWidth(8*scaleFactor)
            glBegin(GL_LINES)
            glVertex2f(x1,y1)
            glVertex2f(x2,y1)
            glEnd()
            glLineWidth(1)
            # The scale label.
            glPushMatrix()
            labelPosX= x1
            labelPosY= y1 - (20.*scaleFactor/self.canvas.scale)
            glTranslatef(labelPosX, labelPosY, 0)
            fontScale = scaleFactor / self.canvas.scale
            glScalef(fontScale, fontScale, 1.)
            if (self.scalebar>1.0):
                self.scale_face.render('%d um' % self.scalebar)
            else:
                self.scale_face.render('%.3f um' % self.scalebar)
            glPopMatrix()

        #Draw stage primitives.
        glEnable(GL_LINE_STIPPLE)
        glLineStipple(1, 0xAAAA)
        glColor3f(0.4, 0.4, 0.4)
        glColor3f(0.4, 0.4, 0.4)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        # Reflect x-cordinates.
        glMultMatrixf([-1.,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])
        for primitive in self.primitives:
            primitive.render()
        glPopMatrix()
        glDisable(GL_LINE_STIPPLE)


    # Draw a crosshairs at the specified position with the specified color.
    # By default make the size of the crosshairs be really big.
    # Refactor: this could move to Canvas by eliminating self.crosshairBoxSize,
    # which is only set and used here, and in centerCanvas.
    def drawCrosshairs(self, position, color, size=None, offset=False):
        xSize = ySize = size
        if size is None:
            xSize = ySize = 100000
        x, y = position
        # offset applied for stage position but not marks!
        if offset:
            # if no offset defined we can't apply it!
            if hasattr(self, 'offset'):
                # sign consistancy! Here we have -(x-offset) = -x + offset!
                x = x - self.offset[0]
                y = y - self.offset[1]

        # Draw the crosshairs
        glColor3f(*color)
        glBegin(GL_LINES)
        glVertex2d(-x - xSize, y)
        glVertex2d(-x + xSize, y)
        glVertex2d(-x, y - ySize)
        glVertex2d(-x, y + ySize)
        glEnd()

        glBegin(GL_LINE_LOOP)
        # Draw the box.
        cams = depot.getActiveCameras()
        # if there is a camera us its real pixel count
        if (len(cams) > 0):
            pixel_size = wx.GetApp().Objectives.GetPixelSize()
            width, height = cams[0].getImageSize()
            self.crosshairBoxSize = width * pixel_size
            width = self.crosshairBoxSize
            height = height * pixel_size
        else:
            # else use the default which is 512Xpixel size from objective
            width = self.crosshairBoxSize
            height = self.crosshairBoxSize

        for i, j in [(-1, -1), (-1, 1), (1, 1), (1, -1)]:
            glVertex2d(-x + i * width / 2,
                       y + j * height / 2)
        glEnd()




## This class handles the UI of the mosaic.
class MosaicWindow(wx.Frame, MosaicCommon):
    SHOW_DEFAULT = True
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        ## Prevent r-click on buttons displaying MainWindow context menu.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: None)
        ## Last known location of the mouse.
        self.prevMousePos = None
        ## Last click position of the mouse.
        self.lastClickPos = None
        ## Function to call when tiles are selected.
        self.selectTilesFunc = None
        ## True if we're generating a mosaic.
        self.amGeneratingMosaic = False
        ## Offset (set by objective change)
        self.offset=(0,0)
        ## Event object to control run state of mosaicLoop.
        self.shouldContinue = threading.Event()

        primitive_specs = wx.GetApp().Config['stage'].getlines('primitives', [])
        self.primitives = [Primitive.factory(spec) for spec in primitive_specs]

        ## Camera used for making a mosaic
        self.camera = None

        ## Mosaic tile overlap
        self.overlap = cockpit.util.userConfig.getValue('mosaicTileOverlap',
                                                        default = 0.0)

        ## Size of the box to draw at the center of the crosshairs.
        self.crosshairBoxSize = 0
        ## Color to use when making new Site instances.
        self.siteColor = SITE_COLORS[0][1]
        ## Current selected sites for highlighting with crosshairs.
        self.selectedSites = set()

        ## Parameters defining the focal plane -- a tuple of
        # (point on plane, normal vector to plane).
        self.focalPlaneParams = None

        # Fonts to use for site labels and scale bar.  Keep two
        # separate fonts instead of dynamically changing the font size
        # because changing the font size would mean discarding the
        # glyph textures for that size.
        self.site_face = cockpit.gui.freetype.Face(self, 96)
        self.scale_face = cockpit.gui.freetype.Face(self, 18)

        #default scale bar size is Zero
        self.scalebar = cockpit.util.userConfig.getValue('mosaicScaleBar',
                                                         default= 0)
        ## Maps button names to wx.Button instances.
        self.nameToButton = {}

        sideSizer = wx.BoxSizer(wx.VERTICAL)
        for args in [
                ('Run mosaic', self.displayMosaicMenu, self.continueMosaic,
                 "Generate a map of the sample by stitching together " +
                 "images collected with the current lights and one " +
                 "camera. Click the Abort button to stop. Right-click " +
                 "to continue a previous mosaic."),
                ('Find stage', self.centerCanvas, None,
                 "Center the mosaic view on the stage and reset the " +
                 "zoom level"),
                ('Delete tiles', self.onDeleteTiles, self.onDeleteAllTiles,
                 "Left-click and drag to select mosaic tiles to delete. " +
                 "This can free up graphics memory on the computer. Click " +
                 "this button again when you are done. Right-click to " +
                 "delete every tile in the mosaic."),
                ('Rescale tiles', self.autoscaleTiles,
                 self.displayRescaleMenu,
                 "Rescale each tile's black- and white-point. Left-click " +
                 "to scale each tile individually. Right-click to select " +
                 "a camera's scaling to use instead."),
                ('Save mosaic', self.saveMosaic, None,
                 "Save the mosaic to disk, so it can be recovered later. " +
                 "This will generate two files: a .txt file and a .mrc " +
                 "file. Load the .txt file to recover the mosaic."),
                ('Load mosaic', self.loadMosaic, None,
                 "Load a mosaic file that was previously saved. Make " +
                 "certain you load the .txt file, not the .mrc file."),
                ('Calculate focal plane', self.setFocalPlane, self.clearFocalPlane,
                 "Calculate the focal plane of the sample, assuming that " +
                 "the currently-selected sites are all in focus, and that " +
                 "the sample is flat. Right-click to clear the focal plane settings." +
                 "Once the focal plane is set, all motion in the mosaic " +
                 "window (including when making mosaics) will stay in the " +
                 "focal plane."),
                ('Mark bead centers', self.selectTilesForBeads, None,
                 "Allows you to select mosaic tiles and search for isolated " +
                 "beads in them. A site will be placed over each one. This " +
                 "is useful for collecting PSFs.")]:
            button = self.makeButton(self, *args)
            sideSizer.Add(button, 0, wx.EXPAND)

        ## Panel for controls dealing with specific sites.
        self.sitesPanel = wx.Panel(self, style = wx.BORDER_SUNKEN)
        sitesSizer = wx.BoxSizer(wx.VERTICAL)
        ## Holds a list of sites.
        self.sitesBox = wx.ListBox(self.sitesPanel,
                                   style=wx.LB_EXTENDED|wx.LB_SORT)
        self.sitesBox.Bind(wx.EVT_LISTBOX, self.onSelectSite)
        self.sitesBox.Bind(wx.EVT_LISTBOX_DCLICK, self.onDoubleClickSite)
        events.subscribe('new site', self.onNewSiteCreated)
        events.subscribe('site deleted', self.onSiteDeleted)
        sitesSizer.Add(self.sitesBox, 1, wx.EXPAND)

        for args in [
                ('Mark site', self.saveSite, self.displaySiteMakerMenu,
                 "Remember the current stage position for later. " +
                 "Right-click to change the marker color."),
                ('Make grid of sites',
                 lambda *args: cockpit.gui.dialogs.gridSitesDialog.showDialog(self),
                 None, "Generate a 2D array of sites."),
                ('Delete selected sites', self.deleteSelectedSites, None,
                 "Delete the selected sites."),
                ('Adjust selected sites', self.offsetSelectedSites, None,
                 'Move the selected sites by some offset.'),
                ('Save sites to file', self.saveSitesToFile, None,
                 'Save the site positions to a file for later recovery.'),
                ('Load saved sites', self.loadSavedSites, None,
                 'Load sites from a file previously generated by the "Save sites to file" button.')
                ]:
            button = self.makeButton(self.sitesPanel, *args)
            sitesSizer.Add(button, 0, wx.EXPAND)

        self.sitesPanel.SetSizerAndFit(sitesSizer)
        sideSizer.Add(self.sitesPanel, 1, wx.EXPAND)
        sizer.Add(sideSizer, 0, wx.EXPAND)

        # The MosaicCanvas can't figure out its own best size so it
        # just disappears after Fit.  We suggest its width to be 3/4
        # of the window width.
        side_panel_size = sideSizer.ComputeFittingClientSize(self)
        canvas_size = (side_panel_size[0] * 3, side_panel_size[1])

        ## MosaicCanvas instance.
        limits = cockpit.interfaces.stageMover.getHardLimits()[:2]
        self.canvas = canvas.MosaicCanvas(self, limits, self.drawOverlay,
                                          self.onMouse, size=canvas_size)
        sizer.Add(self.canvas, 1, wx.EXPAND)

        self.SetSizerAndFit(sizer)

        events.subscribe(events.STAGE_POSITION, self.onAxisRefresh)
        events.subscribe('soft safety limit', self.onAxisRefresh)

        abort_emitter = cockpit.gui.EvtEmitter(self, events.USER_ABORT)
        abort_emitter.Bind(cockpit.gui.EVT_COCKPIT, self.onAbort)

        wx.GetApp().Objectives.Bind(
            cockpit.interfaces.EVT_OBJECTIVE_CHANGED,
            self._OnObjectiveChanged,
        )
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        for item in [self, self.canvas, self.sitesPanel]:
            cockpit.gui.keyboard.setKeyboardHandlers(item)

        self.mosaicThread = None

    ## Create a button with the appropriate properties.
    def makeButton(self, parent, label, leftAction, rightAction, helpText,
            size = (-1, -1)):
        button = wx.Button(parent, -1, label, size = size)
        button.SetToolTip(wx.ToolTip(helpText))
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button


    ## Now that we've been created, recenter the canvas.
    def centerCanvas(self, event = None):
        curPosition = cockpit.interfaces.stageMover.getPosition()[:2]

        # Calculate the size of the box at the center of the crosshairs.
        # \todo Should we necessarily assume a 512x512 area here?
        #if we havent previously set crosshairBoxSize (maybe no camera active)
        if (self.crosshairBoxSize == 0):
            self.crosshairBoxSize = 512 * wx.GetApp().Objectives.GetPixelSize()
        self.offset = wx.GetApp().Objectives.GetOffset()
        scale = (150./self.crosshairBoxSize)
        self.canvas.zoomTo(-curPosition[0]+self.offset[0],
                           curPosition[1]-self.offset[1], scale)


    ## Get updated about new stage position info.
    # This requires redrawing the display, if the axis is the X or Y axes.
    def onAxisRefresh(self, axis, *args):
        if axis in [0, 1]:
            # Only care about the X and Y axes.
            wx.CallAfter(self.canvas.Refresh)


    ## User changed the objective in use; resize our crosshair box to suit.
    def _OnObjectiveChanged(self, event: wx.CommandEvent) -> None:
        self.crosshairBoxSize = 512 * wx.GetApp().Objectives.GetPixelSize()
        self.offset = wx.GetApp().Objectives.GetOffset()
        #force a redraw so that the crosshairs are properly sized
        self.Refresh()
        event.Skip()


    ## Handle mouse events.
    def onMouse(self, event):
        if self.prevMousePos is None:
            # We can't perform some operations without having a prior mouse
            # position, so if it doesn't exist yet, we short-circuit the
            # function. Normally we'll set this at the end of the function.
            self.prevMousePos = event.GetPosition()
            return

        mousePos = event.GetPosition()
        if event.LeftDown():
            self.lastClickPos = event.GetPosition()
        elif event.LeftUp() and self.selectTilesFunc is not None:
            # Call the specified function with the given range.
            start = self.canvas.mapScreenToCanvas(self.lastClickPos)
            end = self.canvas.mapScreenToCanvas(self.prevMousePos)
            self.selectTilesFunc((-start[0], start[1]), (-end[0], end[1]))
            self.lastClickPos = None
            self.Refresh()
        # Skip all other inputs while we select tiles.
        if self.selectTilesFunc is None:
            if event.LeftDClick():
                # Double left-click; move to the target position.
                currentTarget = self.canvas.mapScreenToCanvas(mousePos)
                newTarget = (currentTarget[0] + self.offset[0],
                             currentTarget[1] + self.offset[1])
                #Stop mosaic if we are running one.
                if self.amGeneratingMosaic:
                    self.onAbort()
                self.goTo(newTarget)
            elif event.LeftIsDown() and not event.LeftDown():
                # Dragging the mouse with the left mouse button: drag or
                # zoom, as appropriate.
                delta = (mousePos[0] - self.prevMousePos[0],
                        mousePos[1] - self.prevMousePos[1])
                if event.ShiftDown():
                    # Use the vertical component of mouse motion to zoom.
                    zoomFactor = 1 - delta[1] / 100.0
                    self.canvas.multiplyZoom(zoomFactor)
                else:
                    self.canvas.dragView(delta)
                # Clear the currently-selected sites so the user doesn't have
                # to see crosshairs all the time.
                self.selectedSites = set()
            elif event.GetWheelRotation():
                # Adjust zoom, based on the zoom rate.
                delta = event.GetWheelRotation()
                multiplier = 1.002
                if delta < 0:
                    # Invert the scaling direction.
                    multiplier = 2 - multiplier
                    delta *= -1
                self.canvas.multiplyZoom(multiplier ** delta)
        if event.RightDown():
            # Display a context menu.
            menu = wx.Menu()
            menuId = 1
            for label, color in SITE_COLORS:
                menu.Append(menuId, "Mark site with %s marker" % label)
                self.Bind(wx.EVT_MENU,
                          lambda event, color = color: self.saveSite(color),
                          id=menuId)
                menuId += 1
            menu.AppendSeparator()
            menu.Append(menuId, "Set mosaic tile overlap")
            self.Bind(wx.EVT_MENU,
                      lambda event: self.setTileOverlap(),
                      id=menuId)
            menuId += 1
            menu.Append(menuId, "Toggle mosaic scale bar")
            self.Bind(wx.EVT_MENU,
                      lambda event: self.togglescalebar(),
                      id=menuId)

            cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)

        self.prevMousePos = mousePos

        if self.selectTilesFunc is not None:
            # Need to draw the box the user is drawing.
            self.Refresh()

        # HACK: switch focus to the canvas away from our listbox, otherwise
        # it will seize all future scrolling events.
        if self.IsActive():
            self.canvas.SetFocus()


    ## This generator function creates a clockwise spiral pattern.
    def mosaicStepper(self):
        directions = [(0, -1), (-1, 0), (0, 1), (1, 0)]
        curSpiralSize = 1
        lastX = lastY = 0
        i = 0
        while True:
            dx, dy = directions[i % 4]
            dx *= 1 - (self.overlap / 100.)
            dy *= 1 - (self.overlap / 100.)
            for j in range(1, curSpiralSize + 1):
                yield (lastX + dx * j, lastY + dy * j)
            lastX += dx * curSpiralSize
            lastY += dy * curSpiralSize
            if i % 2:
                curSpiralSize += 1
            i += 1


    ## Toggle run / stop state of the mosaicLoop.
    def toggleMosaic(self):
        if self.mosaicThread is None or not self.mosaicThread.is_alive():
            self.shouldReconfigure = True
            self.shouldRestart = True
            self.mosaicThread = threading.Thread(target=self.mosaicLoop, name="mosaic")
            self.mosaicThread.start()
        if self.shouldContinue.is_set():
            self.shouldContinue.clear()
        else:
            self.shouldContinue.set()


    # Detect stage movement when paused and flag that the mosaic loop
    # should start a new spiral if the stage has moved.
    def onStageMoveWhenPaused(self, axis, position):
        if axis == 2:
            return
        events.unsubscribe(events.STAGE_POSITION, self.onStageMoveWhenPaused)
        self.shouldRestart = True


    ## Generate a spiral mosaic.
    # \param camera Handler of the camera we're collecting images from.
    def generateMosaic(self, camera):
        self.camera = camera
        self.toggleMosaic()


    ## Move the stage in a spiral pattern, stopping to take images at regular
    # intervals, to generate a stitched-together high-level view of the stage
    # contents.
    def mosaicLoop(self):
        from sys import stderr
        stepper = self.mosaicStepper()
        target = None
        while True:
            if not self.shouldContinue.is_set():
                ## Enter idle state.
                # Update button label in main thread.
                events.publish("mosaic stop")
                wx.CallAfter(self.nameToButton['Run mosaic'].SetLabel, 'Run mosaic')
                # Detect stage movement so know whether to start new spiral on new position.
                events.subscribe(events.STAGE_POSITION, self.onStageMoveWhenPaused)
                # Wait for shouldContinue event.
                self.shouldContinue.wait()
                # Clear subscription
                events.unsubscribe(events.STAGE_POSITION, self.onStageMoveWhenPaused)
                # Update button label in main thread.
                wx.CallAfter(self.nameToButton['Run mosaic'].SetLabel, 'Stop mosaic')
                # Set reconfigure flag: cameras or objective may have changed.
                self.shouldReconfigure = True
                events.publish("mosaic start")
                # Catch case that stage has moved but user wants to continue mosaic.
                if not self.shouldRestart and target is not None:
                    self.goTo(target, True)

            if self.shouldRestart:
                # Start a new spiral about current stage position.
                stepper = self.mosaicStepper()
                pos = cockpit.interfaces.stageMover.getPosition()
                centerX = pos[0] - self.offset[0]
                centerY = pos[1] + self.offset[1]
                self.shouldRestart = False

            if self.shouldReconfigure:
                #  Check that camera is valid
                active = depot.getActiveCameras()
                if len(active) == 0:
                    self.shouldContinue.clear()
                    stderr.write("Mosaic stopping: no active cameras.\n")
                    continue
                camera = self.camera
                # Fallback to 0th active camera.
                if camera not in active:
                    camera = active[0]
                # Set image width and height based on camera and objective.
                pixel_size = wx.GetApp().Objectives.GetPixelSize()
                width, height = camera.getImageSize()
                width *= pixel_size
                height *= pixel_size
                self.offset = wx.GetApp().Objectives.GetOffset()
                # Successfully reconfigured: clear the flag.
                self.shouldReconfigure = False

            pos = cockpit.interfaces.stageMover.getPosition()
            curZ = pos[2] - self.offset[2]
            # Take an image. Use timeout to prevent getting stuck here.
            try:
                data, timestamp = events.executeAndWaitForOrTimeout(
                    events.NEW_IMAGE % camera.name,
                    wx.GetApp().Imager.takeImage,
                    camera.getExposureTime()/1000 + CAMERA_TIMEOUT,
                    shouldBlock=True)
            except Exception as e:
                # Go to idle state.
                self.shouldContinue.clear()
                stderr.write("Mosaic stopping - problem taking image: %s\n" % str(e))
                continue

            # Get the scaling for the camera we're using, since they may
            # have changed.
            try:
                minVal, maxVal = cockpit.gui.camera.window.getCameraScaling(camera)
                # HACK: If this is the first image being acquired the
                # viewCanvas has not yet set the scaling.  Its default
                # of [0 1] is unlikely to be appropriate for images
                # that are likely uint8/16.  So wait a bit and read it
                # again.  We should either be deciding the scaling
                # ourselves, or get an image with associated scaling
                # information or after the scaling information has
                # been set.  See issue #718.
                if (minVal == 0.0) and (maxVal == 1.0):
                    time.sleep(0.1)
                    minVal, maxVal = cockpit.gui.camera.window.getCameraScaling(camera)
            except Exception as e:
                # Go to idle state.
                self.shouldContinue.clear()
                stderr.write("Mosaic stopping - problem in getCameraScaling: %s\n" % str(e))
                continue

            # Paint the tile at the stage position at which image was captured.
            self.canvas.addImage(data,
                                 ( -pos[0] + self.offset[0] - width / 2,
                                    pos[1] - self.offset[1] - height / 2,
                                    curZ,),
                                 (width, height), scalings=(minVal, maxVal))
            # Move to the next position in shifted coords.
            dx, dy = next(stepper)
            target = (centerX + self.offset[0] + dx * width,
                      centerY - self.offset[1] + dy * height)
            try:
                self.goTo(target, True)
            except Exception as e:
                self.shouldContinue.clear()
                stderr.write("Mosaic stopping - problem in target calculation: %s\n" % str(e))
                continue


    ## Display dialogue box to set tile overlap.
    def setTileOverlap(self):
        value = cockpit.gui.dialogs.getNumberDialog.getNumberFromUser(
                    self.GetParent(),
                    "Set mosaic tile overlap.",
                    "Tile overlap in %",
                    self.overlap,
                    atMouse=True)
        self.overlap = float(value)
        cockpit.util.userConfig.setValue('mosaicTileOverlap', self.overlap)


    ## Transfer an image from the active camera (or first camera) to the
    # mosaic at the current stage position.
    def transferCameraImage(self):
        camera = self.camera
        if camera is None or not camera.getIsEnabled():
            # Select the first active camera.
            for cam in depot.getHandlersOfType(depot.CAMERA):
                if cam.getIsEnabled():
                    camera = cam
                    break
        # Get image size in microns.
        pixel_size = wx.GetApp().Objectives.GetPixelSize()
        width, height = camera.getImageSize()
        width *= pixel_size
        height *= pixel_size
        x, y, z = cockpit.interfaces.stageMover.getPosition()
        data = cockpit.gui.camera.window.getImageForCamera(camera)
        self.canvas.addImage(data, (-x +self.offset[0]- width / 2,
                                    y-self.offset[1] - height / 2,
                                    z-self.offset[2]),
                (width, height),
                scalings = cockpit.gui.camera.window.getCameraScaling(camera))
        self.Refresh()

    def togglescalebar(self):
        #toggle the scale bar between 0 and 1.
        if (self.scalebar!=0):
            self.scalebar = 0
        else:
            self.scalebar = 1
        #store current state for future.
        cockpit.util.userConfig.setValue('mosaicScaleBar',self.scalebar)
        self.Refresh()

    ## Save the current stage position as a new site with the specified
    # color (or our currently-selected color if none is provided).
    def saveSite(self, color = None):
        if color is None:
            color = self.siteColor
        position = cockpit.interfaces.stageMover.getPosition()
        position[0]=position[0]-self.offset[0]
        position[1]=position[1]-self.offset[1]
        position[2]=position[2]-self.offset[2]
        cockpit.interfaces.stageMover.saveSite(
                cockpit.interfaces.stageMover.Site(position, None, color,
                        size = self.crosshairBoxSize))
        # Publish mosaic update event to update this and other views (e.g. touchscreen).
        events.publish(events.MOSAIC_UPDATE)


    ## Set the site marker color.
    def setSiteColor(self, color):
        self.siteColor = color
        for label, altColor in SITE_COLORS:
            if altColor == color:
                self.nameToButton['Mark site'].SetLabel('Mark site (%s)' % label)
                break


    ## Display a menu that allows the user to control the appearance of
    # the markers used to mark sites.
    def displaySiteMakerMenu(self, event = None):
        menu = wx.Menu()
        for i, (label, color) in enumerate(SITE_COLORS):
            menu.Append(i + 1, "Mark sites in %s" % label)
            self.Bind(wx.EVT_MENU,
                      lambda event, color = color: self.setSiteColor(color),
                      id=i+1)
        cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)


    ## Calculate the focal plane of the sample.
    def setFocalPlane(self, event = None):
        sites = self.getSelectedSites()
        positions = [s.position for s in sites]
        if len(positions) < 3:
            wx.MessageDialog(self,
                    "Please select at least 3 in-focus sites.",
                    "Insufficient input.").ShowModal()
            return
        positions = numpy.array(positions)
        # Pick a point in the plane, as the average of all site positions.
        center = positions.mean(axis = 0)
        # Try every combinations of points, and average their resulting normal
        # vectors together.
        normals = []
        for i in range(len(positions)):
            p1 = positions[i] - center
            for j in range(i + 1, len(positions)):
                p2 = positions[j] - center
                for k in range(j + 1, len(positions)):
                    p3 = positions[k] - center
                    # Calculate normal vector, and normalize
                    normal = numpy.cross(p2 - p1, p3 - p1)
                    magnitude = numpy.sqrt(sum(normal * normal))
                    normals.append(normal / magnitude)

        # Ensure all normals point in the same direction. If they oppose,
        # their sum should be ~0; if they are aligned, it should be
        # ~2.
        normals = numpy.array(normals)
        base = normals[0]
        for normal in normals[1:]:
            if sum(base + normal) < .5:
                # Opposed normals.
                normal *= -1
        self.focalPlaneParams = (center, normals.mean(axis = 0))
        deltas = []
        for site in sites:
            pos = numpy.array(site.position)
            z = self.getFocusZ(pos)
            deltas.append(pos[2] - z)
            print ("Delta for",pos,"is",(pos[2] - z))
        print ("Average delta is",numpy.mean(deltas),"with std",numpy.std(deltas))


    ## Clear the focal plane settings.
    def clearFocalPlane(self):
        self.focalPlaneParams = None


    ## Calculate the Z position in focus for a given XY position, according
    # to our focal plane parameters.
    def getFocusZ(self, point):
        center, normal = self.focalPlaneParams
        point = numpy.array(point)
        z = -numpy.dot(normal[:2], point[:2] - center[:2]) / normal[2] + center[2]
        return z


    ## User clicked on a site in the sites box; draw a crosshairs on it.
    # \todo Enforcing int site IDs here.
    def onSelectSite(self, event = None):
        self.selectedSites = set()
        for item in self.sitesBox.GetSelections():
            text = self.sitesBox.GetString(item)
            siteID = int(text.split(':')[0])
            self.selectedSites.add(cockpit.interfaces.stageMover.getSite(siteID))
        # Refresh this and other mosaic views.
        events.publish(events.MOSAIC_UPDATE)


    ## User double-clicked on a site in the sites box; go to that site.
    # \todo Enforcing int site IDs here.
    def onDoubleClickSite(self, event):
        item = event.GetString()
        siteID = int(item.split(':')[0])
        cockpit.interfaces.stageMover.goToSite(siteID)


    ## Return a list of of the currently-selected Sites.
    def getSelectedSites(self):
        result = []
        for item in self.sitesBox.GetSelections()[::-1]:
            text = self.sitesBox.GetString(item)
            siteID = int(text.split(':')[0])
            result.append(cockpit.interfaces.stageMover.getSite(siteID))
        return result


    ## Delete the sites the user has selected in our sitebox.
    def deleteSelectedSites(self, event = None):
        # Go in reverse order so that removing items from the box doesn't
        # invalidate future indices.
        for item in self.sitesBox.GetSelections()[::-1]:
            text = self.sitesBox.GetString(item)
            siteID = int(text.split(':')[0])
            self.selectedSites.remove(cockpit.interfaces.stageMover.getSite(siteID))
            cockpit.interfaces.stageMover.deleteSite(siteID)
            self.sitesBox.Delete(item)
        ## Deselect everything to work around issue #408 (under gtk,
        ## deleting items will move the selection to the next item)
        self.sitesBox.SetSelection(wx.NOT_FOUND)
        self.Refresh()


    ## Move the selected sites by an offset.
    def offsetSelectedSites(self, event = None):
        items = self.sitesBox.GetSelections()
        if not items:
            # No selected sites.
            return
        offset = cockpit.gui.dialogs.offsetSitesDialog.showDialogModal(self)
        if offset is not None:
            for item in items:
                siteID = int(self.sitesBox.GetString(item).split(':')[0])
                site = cockpit.interfaces.stageMover.getSite(siteID)
                # Account for the fact that the site position may be a
                # (non-mutable) tuple; cast it to a list before modifying it.
                position = list(site.position)
                for axis, value in enumerate(offset):
                    position[axis] += value
                site.position = tuple(position)
            # Redisplay the sites in the sitesbox.
            self.sitesBox.Clear()
            for site in cockpit.interfaces.stageMover.getAllSites():
                self.onNewSiteCreated(site, shouldRefresh = False)
            self.Refresh()


    ## Save sites to a file.
    def saveSitesToFile(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = "Please select where to save the file.",
                defaultDir = cockpit.util.files.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            return
        cockpit.interfaces.stageMover.writeSitesToFile(dialog.GetPath())


    ## Load sites from a file.
    def loadSavedSites(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = "Please select the file to load.",
                defaultDir = cockpit.util.files.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            return
        cockpit.interfaces.stageMover.loadSites(dialog.GetPath())


    ## A new site was created (from any source); add it to our sites box.
    def onNewSiteCreated(self, site, shouldRefresh = True):
        # This display is a bit compressed, so that all positions are visible
        # even if there's a scrollbar in the sites box.
        position = ",".join(["%d" % p for p in site.position])
        label = site.uniqueID
        # HACK: most uniqueID instances will be ints, which we zero-pad
        # so that they stay in appropriate order.
        if type(label) is int:
            label = '%04d' % label
        self.sitesBox.Append("%s: %s" % (label, position))
        if shouldRefresh:
            self.Refresh()


    ## A site was deleted; remove it from our sites box.
    def onSiteDeleted(self, site):
        for item in self.sitesBox.GetItems():
            if site.uniqueID == item:
                self.sitesBox.Delete(item)
                break


    ## Display a menu to the user letting them choose which camera
    # to use to generate a mosaic. Of course, if only one camera is
    # available, then we just do the mosaic.
    def displayMosaicMenu(self):
        # If we're already running a mosaic, stop it instead.
        if self.shouldContinue.is_set():
            self.shouldContinue.clear()
            return

        self.showCameraMenu("Make mosaic with %s camera",
                self.generateMosaic)


    ## Force continuation of mosaic after stage move.
    def continueMosaic(self):
        self.shouldRestart = False
        self.toggleMosaic()


    ## Generate a menu where the user can select a camera to use to perform
    # some action.
    # \param text String template to use for entries in the menu.
    # \param action Function to call with the selected camera as a parameter.
    def showCameraMenu(self, text, action):
        cameras = depot.getActiveCameras()
        if len(cameras) == 0:
            wx.MessageBox("Please enable a camera to run a mosaic.",
                          caption="No cameras are enabled")
        elif len(cameras) == 1:
            action(cameras[0])
        else:
            menu = wx.Menu()
            for i, camera in enumerate(cameras):
                menu.Append(i + 1, text % camera.descriptiveName)
                self.Bind(wx.EVT_MENU,
                          lambda event, camera = camera: action(camera),
                          id=i+1)
            cockpit.gui.guiUtils.placeMenuAtMouse(self, menu)


    ## Set the function to use when the user selects tiles.
    def setSelectFunc(self, func):
        self.selectTilesFunc = func
        self.lastClickPos = None


    ## User clicked the "delete tiles" button; start/stop deleting tiles.
    def onDeleteTiles(self, event = None, shouldForceStop = None):
        amDeleting = 'Stop' not in self.nameToButton['Delete tiles'].GetLabel()
        if shouldForceStop:
            amDeleting = False
        label = ['Delete tiles', 'Stop deleting'][amDeleting]
        self.nameToButton['Delete tiles'].SetLabel(label)
        if amDeleting:
            self.setSelectFunc(self.canvas.deleteTilesIntersecting)
        else:
            self.setSelectFunc(None)


    ## Delete all tiles in the mosaic, after prompting the user for
    # confirmation.
    @_pauseMosaicLoop
    def onDeleteAllTiles(self, event = None):
        if not cockpit.gui.guiUtils.getUserPermission(
                "Are you sure you want to delete every tile in the mosaic?",
                "Delete confirmation"):
            return
        self.canvas.deleteAll()
        self.shouldRestart = True


    ## Rescale each tile according to that tile's own values.
    @_pauseMosaicLoop
    def autoscaleTiles(self, event = None):
        self.canvas.rescale(None)


    ## Let the user select a camera to use to rescale the tiles.
    def displayRescaleMenu(self, event = None):
        self.showCameraMenu("Rescale according to %s camera",
                self.rescaleWithCamera)


    ## Given a camera handler, rescale the mosaic tiles based on that
    # camera's display's black- and white-points.
    @_pauseMosaicLoop
    def rescaleWithCamera(self, camera):
        self.canvas.rescale(cockpit.gui.camera.window.getCameraScaling(camera))


    ## Save the mosaic to disk. We generate a text file describing the
    # locations of the mosaic tiles, and an MRC file of the tiles themselves.
    def saveMosaic(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = "Please select where to save the file.",
                defaultDir = cockpit.util.files.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            return
        self.canvas.saveTiles(dialog.GetPath())


    ## Load a mosaic that was previously saved to disk.
    def loadMosaic(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = "Please select the .txt file the mosaic was saved to.")
        if dialog.ShowModal() != wx.ID_OK:
            return
        self.canvas.loadTiles(dialog.GetPath())


    ## Prepare to mark bead centers.
    def selectTilesForBeads(self):
        self.setSelectFunc(self.markBeadCenters)


    ## Examine the mosaic, trying to find isolated bead centers, and putting
    # a site marker on each one. We partition each tile of the mosaic into
    # subsections, find connected components, and mark them if they
    # are isolated.
    def markBeadCenters(self, start, end):
        # Cancel selecting beads now that we have what we need.
        self.setSelectFunc(None)
        tiles = self.canvas.getTilesIntersecting(start, end)
        statusDialog = wx.ProgressDialog(parent = self,
                title = "Finding bead centers",
                message = "Scanning mosaic...",
                maximum = len(tiles),
                style = wx.PD_CAN_ABORT)
        statusDialog.Show()
        regionSize = 300
        # List of BeadSite instances for potential beads
        beadSites = []
        for i, tile in enumerate(tiles):
            # NB shouldSkip is always false because we don't provide a skip
            # button.
            shouldContinue, shouldSkip = statusDialog.Update(i)
            if not shouldContinue:
                # User cancelled.
                break
            try:
                data = self.canvas.getCompositeTileData(tile, tiles)
            except Exception as e:
                print ("Failed to get tile data at %s: %s" % (tile.pos, e))
                break
            pixelSize = tile.getPixelSize()
            median = numpy.median(data)
            std = numpy.std(data)
            # Threshold the data so that background becomes 0 and signal
            # becomes 1 -- admittedly the threshold value is somewhat
            # arbitrary.
            thresholded = numpy.zeros(data.shape, dtype = numpy.uint16)
            thresholded[numpy.where(data > median + std * 15)] = 1

            # Slice up into overlapping regions. Only examine the center
            # portion of the composite image.
            for j in range(data.shape[0] / 3, 2 * data.shape[0] / 3, regionSize / 4):
                for k in range(data.shape[1] / 3, 2 * data.shape[1] / 3, regionSize / 4):
                    region = thresholded[j : j + regionSize, k : k + regionSize]
                    # Skip overly small regions (on the off-chance that
                    # regionSize is a significant portion of the tile size).
                    if region.shape[0] < regionSize or region.shape[1] < regionSize:
                        continue
                    # Find connected components in data.
                    numComponents = scipy.ndimage.measurements.label(region)[1]
                    if numComponents != 1:
                        # More than one bead visible, or no beads at all.
                        continue
                    # Find the centroid of the component
                    yVals, xVals = numpy.where(region == 1)
                    x, y = numpy.mean(xVals), numpy.mean(yVals)
                    # Ensure that the bead is not near the edge, where
                    # it might be close to a bead in a different region. Note
                    # that our region iteration overlaps, so if a bead is truly
                    # isolated we'll pick it up on a different loop.
                    if (x < regionSize * .25 or x > regionSize * .75 or
                            y < regionSize * .25 or y > regionSize * .75):
                        continue
                    # Ensure that the bead is circular, by comparing the area
                    # of the bead to the area of a circle containing all of
                    # the bead's pixels.
                    xDists = [(x - xi) ** 2 for xi in xVals]
                    yDists = [(y - yi) ** 2 for yi in yVals]
                    maxDistSquared = max(map(sum, list(zip(xDists, yDists))))
                    # Area of a circle containing all pixels
                    area = numpy.pi * maxDistSquared
                    # Reject beads whose area is less than 60% of the area of
                    # the circle.
                    if len(xVals) / area < .6:
                        continue

                    # Go from the subregion coordinates to full-tile coordinates
                    x += k - data.shape[1] / 3
                    y += j - data.shape[0] / 3
                    pos = numpy.array([-tile.pos[0] - x * pixelSize[0],
                            tile.pos[1] + y * pixelSize[1],
                            tile.pos[2]])
                    # Check for other marked beads that are close to this one.
                    # \todo This process makes the entire system N^2
                    # (where N is the number of sites), so it's moderately
                    # expensive.
                    canKeep = True
                    for site in beadSites:
                        distance = numpy.sqrt(sum((pos - site.pos) ** 2))
                        if distance < 40:
                            # Within 40 microns of another bead; skip it.
                            canKeep = False
                            break
                    if not canKeep:
                        continue
                    # Record this potential bead. Its "size" is the number
                    # of pixels in the component, and its intensity is the
                    # average intensity of pixels in the component.
                    newSite = BeadSite(pos, len(xVals),
                            numpy.mean(data[(yVals, xVals)]))
                    beadSites.append(newSite)

        # Examine our bead sites and reject ones that are:
        # - too large (probably conjoined or overlapping beads)
        # - too bright (ditto)
        # - too dim (bad signal:noise ratio)
        # - too small (Could just be autoflourescing dust or something)
        # Part of the trick here is that many beads may be slightly out of
        # focus, so these constraints can't actually be all that tight.
        sizes = numpy.array([b.size for b in beadSites])
        sizeMedian = numpy.median(sizes)
        sizeStd = numpy.std(sizes)
        intensities = numpy.array([b.intensity for b in beadSites])
        intenMedian = numpy.median(intensities)
        intenStd = numpy.std(intensities)
        siteQueue = []
        for i, site in enumerate(beadSites):
            if (site.size < sizeMedian - sizeStd * .5 or
                    site.size > sizeMedian + sizeStd * 2):
                # Too big or too small.
                continue
            if abs(site.intensity - intenMedian) > intenStd * 5:
                # Wrong brightness.
                continue
            siteQueue.append(site.pos)

        # Scan each site in Z to get perfect focus. Look up/down +- 1 micron,
        # and pick the Z altitude with the brightest image.
        # HACK: use the first active camera we find.
        cameras = depot.getHandlersOfType(depot.CAMERA)
        camera = None
        for alt in cameras:
            if alt.getIsEnabled():
                camera = alt
                break
        for x, y, z in siteQueue:
            bestOffset = 0
            bestIntensity = None
            for offset in numpy.arange(-1, 1.1, .1):
                cockpit.interfaces.stageMover.goTo((x, y, z + offset), shouldBlock = True)
                image, timestamp = events.executeAndWaitFor(events.NEW_IMAGE % camera.name,
                        wx.GetApp().Imager.takeImage, shouldBlock = True)
                if bestIntensity is None or image.max() > bestIntensity:
                    bestIntensity = image.max()
                    bestOffset = offset
            newSite = cockpit.interfaces.stageMover.Site((x, y, z + bestOffset),
                    group = 'beads', size = 2)
            wx.CallAfter(cockpit.interfaces.stageMover.saveSite, newSite)
        statusDialog.Destroy()
        wx.CallAfter(self.Refresh)


    ## Handle the user clicking the abort button.
    def onAbort(self, *args):
        self.shouldContinue.clear()
        # Stop deleting tiles, while we're at it.
        self.onDeleteTiles(shouldForceStop = True)



## Global window singleton.
window = None


def makeWindow(parent):
    global window
    window = MosaicWindow(parent, title="Mosaic view")
    window.centerCanvas()


## Transfer a camera image to the mosaic.
def transferCameraImage():
    window.transferCameraImage()
