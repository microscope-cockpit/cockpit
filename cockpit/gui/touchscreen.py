#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018-2019 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
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

import collections
from cockpit.util import ftgl
import numpy
import os, sys
import wx
from wx.lib.agw.shapedbutton import SButton, SBitmapButton,SBitmapToggleButton
from cockpit.gui.toggleButton import ACTIVE_COLOR, INACTIVE_COLOR
from cockpit.handlers.deviceHandler import STATES

import cockpit.gui.macroStage.macroStageBase
from cockpit.gui.macroStage.macroStageXY import MacroStageXY
from cockpit.gui.macroStage.macroStageZ import MacroStageZ
from cockpit import depot
from cockpit import events
import cockpit.gui
import cockpit.gui.camera.window
import cockpit.gui.dialogs.gridSitesDialog
import cockpit.gui.dialogs.offsetSitesDialog
import cockpit.gui.guiUtils
import cockpit.gui.keyboard
import cockpit.gui.mosaic.window as mosaic
import cockpit.gui.mosaic.canvas
import cockpit.interfaces.stageMover
import cockpit.util.colors
import cockpit.util.threads
import cockpit.util.userConfig
from cockpit.gui.saveTopBottomPanel import moveZCheckMoverLimits

## Size of the crosshairs indicating the stage position.
CROSSHAIR_SIZE = 10000
## Valid colors to use for site markers.
SITE_COLORS = [('green', (0, 1, 0)), ('red', (1, 0, 0)),
    ('blue', (0, 0, 1)), ('orange', (1, .6, 0))]

## Width of widgets in the sidebar.
SIDEBAR_WIDTH = 150
BACKGROUND_COLOUR = (160,160,160)

## Timeout for mosaic new image events
CAMERA_TIMEOUT = 5
##how good a circle to draw
CIRCLE_SEGMENTS = 32
PI = 3.141592654

## Simple structure for marking potential beads.
BeadSite = collections.namedtuple('BeadSite', ['pos', 'size', 'intensity'])


class SetVariable(wx.Window):
    def __init__(self, parent):
        super().__init__(parent, wx.ID_ANY)
        self._value = 0.
        self._units = ''
        self.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Create decrement and increment buttons.
        decButton = SButton(self, -1, '-')
        incButton = SButton(self, -1, '+')
        bfont = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        for b in (incButton, decButton):
            b.SetFont(bfont)
            # GetBestSize produces a size that is 3 times wider than it needs to be,
            # so set size to the smaller dimension.
            s = b.DoGetBestSize()
            b.SetSize(min(s), min(s))
        decButton.Bind(wx.EVT_BUTTON, lambda evt: self._spin(-1))
        incButton.Bind(wx.EVT_BUTTON, lambda evt: self._spin(1))
        # Create a text display of width to fit text like "00.000 uuu"
        self._text = wx.StaticText(self, -1, label="00.000 uuu", style=wx.ST_NO_AUTORESIZE | wx.ALIGN_CENTER)
        self._text.SetFont(wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        # Add text to its own sizer with stretch spacers to centre vertically.
        tsizer = wx.BoxSizer(wx.VERTICAL)
        tsizer.AddStretchSpacer()
        tsizer.Add(self._text, 0, wx.EXPAND)
        tsizer.AddStretchSpacer()
        # Pack into sizer as " -  00.000 uu  + "
        self.Sizer.Add(decButton, 0, wx.FIXED_MINSIZE, 0)
        self.Sizer.Add(tsizer, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        self.Sizer.Add(incButton, 0, wx.FIXED_MINSIZE, 0)
        self.Fit()

    def _spin(self, direction):
        if direction not in (-1, 1):
            raise Exception("Expected +1 or -1.")
        evt = wx.SpinDoubleEvent(wx.wxEVT_SPINCTRLDOUBLE)
        evt.SetValue(self._value * (1 + 0.1*direction))
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

    def SetValue(self, value):
        self._value = value
        self.Refresh()

    def SetUnits(self, units):
        self._units = units
        self.Refresh()

    def Refresh(self):
        self._text.SetLabel("%5.2f %s" % (self._value, self._units) )
        super().Refresh()


## This class handles the UI of the mosaic.
class TouchScreenWindow(wx.Frame, mosaic.MosaicCommon):
    ## A number of properties are needed to fetch live values from the mosaic
    # window. These are used in MosaicWindow methods that are rebound to
    # our instance here to duplicate the same view.

    @property
    def selectedSites(self):
        return mosaic.window.selectedSites

    @property
    def primitives(self):
        return mosaic.window.primitives

    @property
    def focalPlaneParams(self):
        return mosaic.window.focalPlaneParams


    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)
        self.panel = wx.Panel(self)
        self.masterMosaic=mosaic.window
        sizer = wx.BoxSizer(wx.HORIZONTAL)


        ## Last known location of the mouse.
        self.prevMousePos = None
        ## Last click position of the mouse.
        self.lastClickPos = None
        ## Function to call when tiles are selected.
        self.selectTilesFunc = None

        ## Size of the box to draw at the center of the crosshairs.
        self.crosshairBoxSize = 0


        ## Font to use for site labels.
        self.sitefont = ftgl.TextureFont(cockpit.gui.FONT_PATH)
        self.defaultFaceSize = 64
        self.sitefont.setFaceSize(self.defaultFaceSize)

        ## A font to use for the scale bar.
        # We used to resize the site font dynamically to do this,
        # but it seems to break on some GL implementations so that
        # the default face size was not restored correctly.
        self.scalefont = ftgl.TextureFont(cockpit.gui.FONT_PATH)
        self.scalefont.setFaceSize(18)

        #default scale bar size is Zero
        self.scalebar = cockpit.util.userConfig.getValue('mosaicScaleBar',
                                                         default=0)
        #Default to drawing primitives
        self.drawPrimitives = cockpit.util.userConfig.getValue('mosaicDrawPrimitives',
                                                               default = True)

        ##define text strings to change status strings.
        self.sampleStateText=None
        ## Maps button names to wx.Button instances.
        self.nameToButton = {}
        self.nameToText={}
        self.bitmapsPath = cockpit.gui.BITMAPS_PATH

        self.buttonPanel=wx.Panel(self.panel, -1, size=(300,-1),
                                  style=wx.BORDER_RAISED)
        self.buttonPanel.SetBackgroundColour(BACKGROUND_COLOUR)
        self.buttonPanel.SetDoubleBuffered(True)
        ##right side sizer is the button bar on right side of ts window
        rightSideSizer = wx.BoxSizer(wx.VERTICAL)


        ## objectiveSizer at top of rightSideSizer for objective stuff
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
#        font=wx.Font(12,wx.FONTFAMILY_DEFAULT, wx.FONTWEIGHT_NORMAL,
#                     wx.FONTSTYLE_NORMAL)
        objectiveSizer=wx.GridSizer(2, 2, 1)

        button = self.makeToggleButton(self.buttonPanel, 'Load/Unload',
                                       self.loadUnload, None,
                                       'load.png','unload.png',
                 "Load or unload the sample from approximate in focus "+
                 "Z position",(75,75))
        objectiveSizer.Add(button, 0, wx.EXPAND|wx.ALL, border=5)

        textSizer=wx.BoxSizer(wx.VERTICAL)
        sampleText=wx.StaticText(self.buttonPanel,-1,'Sample',style=wx.ALIGN_CENTER)
        sampleText.SetFont(font)
        textSizer.Add(sampleText, 0, wx.EXPAND|wx.ALL, border=5)

        self.sampleStateText=wx.StaticText(self.buttonPanel,-1,style=wx.ALIGN_CENTER)
        self.sampleStateText.SetFont(font)
        #empty call to set the default sample state
        self.setSampleStateText()

        textSizer.Add(self.sampleStateText, 0, wx.EXPAND|wx.ALL, border=5)

        #objective swithcing control and text
        objectiveSizer.Add(textSizer,0,wx.EXPAND|wx.ALL,border=5)
        button = self.makeButton(self.buttonPanel,  'Change Objective',
                                       self.changeObjective, None,
                                       'change_objective.png',
                                       "Change the objective",(75,75))
        objectiveSizer.Add(button, 0, wx.EXPAND|wx.ALL, border=5)

        textSizer2=wx.BoxSizer(wx.VERTICAL)
        objectiveText=wx.StaticText(self.buttonPanel,-1,'Objective',
                                    style=wx.ALIGN_CENTER)
        objectiveText.SetFont(font)
        textSizer2.Add(objectiveText, 0, wx.EXPAND|wx.ALL,border=5)

        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]

        self.objectiveSelectedText=wx.StaticText(self.buttonPanel,-1,
                                                 style=wx.ALIGN_CENTER)
        self.objectiveSelectedText.SetFont(font)
        self.objectiveSelectedText.SetLabel(objective.curObjective.center(15))

        colour = tuple(map(lambda x: 255*x, objective.getColour()))
        self.sampleStateText.SetBackgroundColour(colour)
        textSizer2.Add(self.objectiveSelectedText, 0, wx.CENTER|wx.ALL,border=5)

        objectiveSizer.Add(textSizer2, 0, wx.EXPAND|wx.ALL, border=5)

        ##mosaic control button panel
        mosaicButtonSizer=wx.GridSizer(2, 2, 1)

        for args in [('Run mosaic',self.displayMosaicMenu,
                      self.continueMosaic,
                      'run_mosaic.png','stop_mosaic.png',
                 "Generate a map of the sample by stitching together " +
                 "images collected with the current lights and one " +
                 "camera. Click the Abort button to stop. Right-click " +
                      "to continue a previous mosaic.",
                      (75,75)),
                     ('Find stage', self.centerCanvas, None,
                      'centre_view.png',
                      "Center the mosaic view on the stage and reset the " +
                      "zoom level"),
                     ('Delete tiles', self.onDeleteTiles, self.onDeleteAllTiles,
                      'erase_tiles.png','erase_tiles-active.png',
                "Left-click and drag to select mosaic tiles to delete. " +
                "This can free up graphics memory on the computer. Click " +
                "this button again when you are done. Right-click to " +
                      "delete every tile in the mosaic.",(75,75)),
                     ('Snap Image', self.snapImage, None,
                      'snap_image.png',
                "Click to snap an image at the current stage positon and " +
                      "transfer it directly into the mosaic.")]:

            if len(args) is 7:
                button = self.makeToggleButton(self.buttonPanel, *args)
            elif len(args) is 5:
                button = self.makeButton(self.buttonPanel, *args)
            mosaicButtonSizer.Add(button, 0, wx.EXPAND|wx.ALL,border=2)

        ## laserSizer in middle of rightSideSizer for laser stuff
        lightsSizer = wx.BoxSizer(wx.VERTICAL)
        # Find out light devices we have to work with.
        lightToggles = sorted(depot.getHandlersOfType(depot.LIGHT_TOGGLE),
                              key=lambda l: l.wavelength)
        lightPowers = depot.getHandlersOfType(depot.LIGHT_POWER)
        # Create light controls
        for light in lightToggles:
            # Enable/disable button
            button = LightToggleButton(self.buttonPanel, light)
            # Power control
            powerHandler = next(filter(lambda p: p.groupName == light.groupName, lightPowers), None)
            if powerHandler is not None:
                powerctrl = SetVariable(self.buttonPanel)
                powerctrl.SetBackgroundColour(BACKGROUND_COLOUR)
                powerctrl.SetUnits(powerHandler.units)
                powerctrl.SetValue(powerHandler.powerSetPoint)
                powerctrl.Bind(wx.EVT_SPINCTRLDOUBLE, lambda evt, h=powerHandler: h.setPower(evt.Value) )
                powerHandler.addWatch('powerSetPoint', powerctrl.SetValue)
            # Exposure control
            expctrl = SetVariable(self.buttonPanel)
            expctrl.SetBackgroundColour(BACKGROUND_COLOUR)
            expctrl.SetUnits('ms')
            expctrl.SetValue(light.exposureTime)
            expctrl.Bind(wx.EVT_SPINCTRLDOUBLE, lambda evt, h=light: h.setExposureTime(evt.Value) )
            light.addWatch('exposureTime', expctrl.SetValue)
            # Layout the controls
            rowsizer = wx.BoxSizer(wx.HORIZONTAL)
            ctrlsizer = wx.BoxSizer(wx.VERTICAL)
            rowsizer.Add(button, 0, wx.ALL, border=2)  # AddSizer?
            rowsizer.Add(ctrlsizer, 1, wx.EXPAND | wx.LEFT, 12)
            ctrlsizer.AddStretchSpacer()
            if powerHandler is not None:
                ctrlsizer.Add(powerctrl, 0, wx.EXPAND)
            ctrlsizer.Add(expctrl, 0, wx.EXPAND)
            ctrlsizer.AddStretchSpacer()
            lightsSizer.Add(rowsizer,0,wx.EXPAND|wx.ALL,border=2)

        cameraSizer=wx.GridSizer(cols=2, vgap=1, hgap=1)
        cameraVSizer=[None]*len(depot.getHandlersOfType(depot.CAMERA))
        self.camButton=[None]*len(depot.getHandlersOfType(depot.CAMERA))
        i=0
        for camera in depot.getHandlersOfType(depot.CAMERA):
            cameraVSizer[i] = wx.BoxSizer(wx.VERTICAL)
            # Remove the word 'camera' to shorten labels.
            name = camera.name.replace('camera', '').replace('  ', ' ')
            label = cockpit.gui.device.Label(
                parent=self.buttonPanel, label=name)
            self.camButton[i] = cockpit.gui.device.EnableButton(self.buttonPanel, camera)
            cameraVSizer[i].Add(label)
            cameraVSizer[i].Add(self.camButton[i])
            cameraSizer.Add(cameraVSizer[i],0,wx.CENTRE|wx.ALL,border=5)
            i=i+1

        rightSideSizer.Add(objectiveSizer,0,wx.EXPAND,wx.SUNKEN_BORDER)
        rightSideSizer.Add(wx.StaticLine(self.buttonPanel),
                           0, wx.ALL|wx.EXPAND, 5)
        rightSideSizer.Add(mosaicButtonSizer,0,wx.EXPAND,wx.RAISED_BORDER)
        rightSideSizer.Add(wx.StaticLine(self.buttonPanel),
                           0, wx.ALL|wx.EXPAND, 5)
        rightSideSizer.Add(lightsSizer,0,wx.EXPAND)
        rightSideSizer.Add(wx.StaticLine(self.buttonPanel),
                           0, wx.ALL|wx.EXPAND, 5)
        rightSideSizer.Add(cameraSizer,0,wx.EXPAND)

        #run sizer fitting on button panel
        self.buttonPanel.SetSizerAndFit(rightSideSizer)
        sizer.Add(self.buttonPanel, 0, wx.EXPAND,wx.RAISED_BORDER)

        limits = cockpit.interfaces.stageMover.getHardLimits()[:2]
        ## start a slaveCanvas instance.
        self.canvas = cockpit.gui.mosaic.canvas.MosaicCanvas(self.panel, limits,
                                                             self.drawOverlay,
                                                             self.onMouse)
        sizer.Add(self.canvas, 3, wx.EXPAND)
        leftSizer= wx.BoxSizer(wx.VERTICAL)
        #add a macrostageXY overview section
        self.macroStageXY = MacroStageXY(self.panel, size=(168, 392), id=-1)
        leftSizer.Add(self.macroStageXY,2, wx.EXPAND)

        ##start a TSmacrostageZ instance
        self.macroStageZ = MacroStageZ(self.panel, size=(168, 392), id=-1)
        leftSizer.Add(self.macroStageZ, 3,wx.EXPAND)

        ## Z control buttons
        zButtonSizer=wx.GridSizer(3, 2, 1, 1)

        for args in [('Up', self.zMoveUp, None,
                      'up.png',
                      "Move up one Z step",(30,30)),
                     ('Inc Step', self.zIncStep, None,
                      'plus.png',
                      "Increase Z step",(30,30))]:
            button = self.makeButton(self.panel, *args)
            zButtonSizer.Add(button, 1, wx.EXPAND|wx.ALL,border=2)
        ##Text of position and step size
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        zPositionText = wx.StaticText(self.panel,-1,
                                      style=wx.ALIGN_CENTER)
        zPositionText.SetFont(font)
        #Read current exposure time and store pointer in
        #self. so that we can change it at a later date
        label = 'Z Pos %5.2f'%(cockpit.interfaces.stageMover.getPosition()[2])
        zPositionText.SetLabel(label.rjust(10))
        self.nameToText['Zpos']=zPositionText
        zButtonSizer.Add(zPositionText, 0, wx.EXPAND|wx.ALL,border=15)
        zStepText = wx.StaticText(self.panel,-1,
                                  style=wx.ALIGN_CENTER)
        zStepText.SetFont(font)
        #Read current exposure time and store pointer in
        #self. so that we can change it at a later date
        label = 'Z Step %5d'%(cockpit.interfaces.stageMover.getCurStepSizes()[2])
        zStepText.SetLabel(label.rjust(10))
        self.nameToText['ZStep']=zStepText
        zButtonSizer.Add(zStepText, 0, wx.EXPAND|wx.ALL, border=15)

        for args in [('Down', self.zMoveDown, None,
                      'down.png',
                      "Move down one Z step",(30,30)),
                     ('DecStep', self.zDecStep, None,
                      'minus.png',
                      "Decrease Z step",(30,30))]:
            button = self.makeButton(self.panel, *args)
            zButtonSizer.Add(button, 0, wx.EXPAND|wx.ALL,border=2)
        leftSizer.Add(zButtonSizer, 1,wx.EXPAND)




        sizer.Add(leftSizer,0,wx.EXPAND)

        self.panel.SetSizerAndFit(sizer)
        self.SetRect((0, 0, 1800, 1000))

        events.subscribe('stage position', self.onAxisRefresh)
        events.subscribe('stage step size', self.onAxisRefresh)
        events.subscribe('stage step index', self.stageIndexChange)
        events.subscribe('soft safety limit', self.onAxisRefresh)
        events.subscribe('objective change', self.onObjectiveChange)
        events.subscribe('mosaic start', self.mosaicStart)
        events.subscribe('mosaic stop', self.mosaicStop)
        events.subscribe('mosaic update', self.mosaicUpdate)



        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        for item in [self, self.panel, self.canvas]:
            cockpit.gui.keyboard.setKeyboardHandlers(item)

    def Refresh(self, *args, **kwargs):
        """Refresh, with explicit refresh of glCanvases on Mac.

        Refresh is supposed to be called recursively on child objects,
        but is not always called for our glCanvases on the Mac. This may
        be due to the canvases not having any invalid regions, but I see
        no way to invalidate a region on demand."""
        super().Refresh(*args, **kwargs)
        if sys.platform == 'darwin':
            wx.CallAfter(self.canvas.Refresh)
            wx.CallAfter(self.macroStageXY.Refresh)
            wx.CallAfter(self.macroStageZ.Refresh)

    ##function ot check if a bitmpa exists or return a generic missing
    ##file bitmap
    def checkBitmap(self,bitmap):
        if (os.path.isfile(os.path.join( self.bitmapsPath, bitmap))):
            bmp=wx.Bitmap(os.path.join( self.bitmapsPath, bitmap),
                          wx.BITMAP_TYPE_ANY)
        else:
            bmp=wx.Bitmap(os.path.join( self.bitmapsPath,
                                        'broken-file.png'),
                          wx.BITMAP_TYPE_ANY)
        return bmp
        
    ## Create a button with the appropriate properties.
    def makeButton(self, parent, label, leftAction, rightAction, bitmap,
                   helpText,size = (75,75)):
        bmp=self.checkBitmap(bitmap)
        button = SBitmapButton(parent, -1, bitmap=bmp, size = size)
        button.SetToolTip(wx.ToolTip(helpText))
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button

    ## Create a button with the appropriate properties.
    def makeToggleButton(self, parent, label, leftAction, rightAction, bitmap,
                         bitmapSelected,helpText,size = (75, 75)):
        bmp=self.checkBitmap(bitmap)
        button = SBitmapToggleButton(parent, -1, bitmap=bmp, size = size)
        bmpSelected=self.checkBitmap(bitmapSelected)
        button.SetBitmapSelected(bmpSelected)

        button.SetToolTip(wx.ToolTip(helpText))
        #Note left action is called with true if down, false if up
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button


    def snapImage(self):
        #check that we have a camera and light source
        cams=0
        lights=0
        cams = len(depot.getActiveCameras())
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            if light.getIsEnabled():
                lights=lights+1
        if (cams is 0) or (lights is 0):
            print ("Snap needs a light and a camera to opperate")
            return

        #take the image
        events.executeAndWaitFor("new image %s" %
                                 (list(cockpit.interfaces.imager.imager.activeCameras)[0].name),
                                 cockpit.interfaces.imager.imager.takeImage,
                                 shouldStopVideo = False)
        mosaic.transferCameraImage()
        self.Refresh()

    def laserToggle(self, event, light, button):
        if event.GetIsDown():
            light.setEnabled(True)
            events.publish(events.LIGHT_SOURCE_ENABLE, light, True)
        else:
            light.setEnabled(False)
            button.SetBackgroundColour(BACKGROUND_COLOUR)
            events.publish(events.LIGHT_SOURCE_ENABLE, light, False)


    def laserPowerUpdate(self, light):
        textString=self.nameToText[light.groupName+'power']
        if light.powerSetPoint is None:
            # Light has no power control
            return
        label = '%5.1f %s'%(light.powerSetPoint, light.units)
        textString.SetLabel(label.rjust(10))
        if light.powerSetPoint and light.lastPower:
            matched = 0.95*light.powerSetPoint < light.lastPower < 1.05*light.powerSetPoint
        else:
            matched = False
        if matched:
            textString.SetBackgroundColour(light.color)
        else:
            textString.SetBackgroundColour(BACKGROUND_COLOUR)
        self.Refresh()

    #Update exposure time text on event.
    def laserExpUpdate(self, source=None):
        # TODO: fix this to use the handler reference passed in source
        # i.e. we *do* know which light is update.

        #Dont know which light is updated so update them all.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        lightToggles = sorted(lightToggles, key = lambda l: l.wavelength)
        for light in lightToggles:
           textString=self.nameToText[light.groupName+'exp']
           label = '%5d ms'%(light.getExposureTime())
           textString.SetLabel(label.rjust(10))

        self.Refresh()

    #function called by minus expsoure time button
    def decreaseLaserExp(self,light):
        currentExp=light.getExposureTime()
        newExposure=int(currentExp*0.9)
        light.setExposureTime(newExposure)

    #function called by plus expsoure time button
    def increaseLaserExp(self,light):
        currentExp=light.getExposureTime()
        newExposure=int(currentExp*1.1)
        light.setExposureTime(newExposure)

    #function called by minus laser power button
    def decreaseLaserPower(self,powerHandler):
        currentSP = powerHandler.powerSetPoint or powerHandler.minPower
        powerHandler.setPower(int(currentSP*0.9))


    #function called by plus expsoure time button
    def increaseLaserPower(self,powerHandler):
        currentSP = powerHandler.powerSetPoint or powerHandler.minPower
        powerHandler.setPower(int(currentSP*1.1))


    ## Now that we've been created, recenter the canvas.
    def centerCanvas(self, event = None):
        curPosition = cockpit.interfaces.stageMover.getPosition()[:2]

        # Calculate the size of the box at the center of the crosshairs.
        # \todo Should we necessarily assume a 512x512 area here?
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        #if we havent previously set crosshairBoxSize (maybe no camera active)
        if (self.crosshairBoxSize == 0):
            self.crosshairBoxSize = 512 * objective.getPixelSize()
        self.offset = objective.getOffset()
        scale = (150./self.crosshairBoxSize)
        self.canvas.zoomTo(-curPosition[0]+self.offset[0],
                           curPosition[1]-self.offset[1], scale)

    #Zbutton functions
    def zMoveUp(self):
        cockpit.interfaces.stageMover.step((0,0,1))
    def zMoveDown(self):
        cockpit.interfaces.stageMover.step((0,0,-1))
    def zIncStep(self):
        cockpit.interfaces.stageMover.changeStepSize(1)
        self.onAxisRefresh(2)
    def zDecStep(self):
        cockpit.interfaces.stageMover.changeStepSize(-1)
        self.onAxisRefresh(2)

    ## Resize our canvas.
    def onSize(self, event):
        csize = self.GetClientSize()
        self.panel.SetClientSize((csize[0], csize[1]))

    ##Called when the stage handler index is chnaged. All we need
    #to do is update the display
    def stageIndexChange(self, *args):
        #call on axis refresh to update the display
        self.onAxisRefresh(2)

    ## Get updated about new stage position info or step size.
    # This requires redrawing the display, if the axis is the X or Y axes.
    def onAxisRefresh(self, axis, *args):
        if axis in [0, 1]:
            # Only care about the X and Y axes.
            wx.CallAfter(self.Refresh)
        if axis is 2:
            #Z axis updates
            posString=self.nameToText['Zpos']
            label = 'Z Pos %5.2f'%(cockpit.interfaces.stageMover.getPosition()[2])
            posString.SetLabel(label.rjust(10))
            stepString=self.nameToText['ZStep']
            label = 'Z Step %5.2f'%(cockpit.interfaces.stageMover.getCurStepSizes()[2])
            stepString.SetLabel(label.rjust(10))
            wx.CallAfter(self.Refresh)

    ## User changed the objective in use; resize our crosshair box to suit.
    def onObjectiveChange(self, name, pixelSize, transform, offset, **kwargs):
        h = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.crosshairBoxSize = 512 * pixelSize
        self.offset = offset
        self.objectiveSelectedText.SetLabel(name.center(15))
        colour = tuple(map(lambda x: 255*x, h.getColour()))
        self.objectiveSelectedText.SetBackgroundColour(colour)

        #force a redraw so that the crosshairs are properly sized
        self.Refresh()


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
                #stop mosaic if we are already running one
                if mosaic.window.amGeneratingMosaic:
                    self.masterMosaic.onAbort(mosaic.window)
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
                self.panel.Bind(wx.EVT_MENU,
                                lambda event, color = color: mosaic.window.saveSite(color), id= menuId)
                menuId += 1
            menu.AppendSeparator()
            menu.Append(menuId, "Set mosaic tile overlap")
            self.panel.Bind(wx.EVT_MENU,
                            lambda event: mosaic.window.setTileOverlap(), id= menuId)
            menuId += 1
            menu.Append(menuId, "Toggle mosaic scale bar")
            self.panel.Bind(wx.EVT_MENU,
                            lambda event: self.togglescalebar(), id= menuId)
            menuId += 1
            menu.Append(menuId, "Toggle draw primitives")
            self.panel.Bind(wx.EVT_MENU,
                            lambda event: self.toggleDrawPrimitives(), id= menuId)

            cockpit.gui.guiUtils.placeMenuAtMouse(self.panel, menu)

        self.prevMousePos = mousePos

        if self.selectTilesFunc is not None:
            # Need to draw the box the user is drawing.
            self.Refresh()

        # HACK: switch focus to the canvas away from our listbox, otherwise
        # it will seize all future scrolling events.
        if self.IsActive():
            self.canvas.SetFocus()


    def togglescalebar(self):
        #toggle the scale bar between 0 and 1.
        if (self.scalebar!=0):
            self.scalebar = 0
        else:
            self.scalebar = 1
        #store current state for future.
        cockpit.util.userConfig.setValue('mosaicScaleBar',self.scalebar)
        self.Refresh()

    def toggleDrawPrimitives(self):
        #toggle the scale bar between 0 and 1.
        if (self.drawPrimitives!=False):
            self.drawPrimitives=False
        else:
            self.drawPrimitives = True
        #store current state for future.
        cockpit.util.userConfig.setValue('mosaicDrawPrimitives',
                                         self.drawPrimitives)
        self.Refresh()


    ## Calculate the Z position in focus for a given XY position, according
    # to our focal plane parameters.
    def getFocusZ(self, point):
        center, normal = self.focalPlaneParams
        point = numpy.array(point)
        z = -numpy.dot(normal[:2], point[:2] - center[:2]) / normal[2] + center[2]
        return z


    ##Wrapper functions to call the main mosaic window version
    def displayMosaicMenu(self):
        self.masterMosaic.displayMosaicMenu()

    def continueMosaic(self):
        self.masterMosaic.continueMosaic()


    ## trap start mosaic event
    def mosaicStart(self):
            self.nameToButton['Run mosaic'].SetValue(True)

    def mosaicStop(self):
            self.nameToButton['Run mosaic'].SetValue(False)

    def mosaicUpdate(self):
        self.Refresh()

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
    def onDeleteAllTiles(self, event = None):
        if not cockpit.gui.guiUtils.getUserPermission(
                "Are you sure you want to delete every tile in the mosaic?",
                "Delete confirmation"):
            return
        self.canvas.deleteAll()


    ##Function to load/unload objective
    def loadUnload(self):
        #toggle to load or unload the sample
        config = wx.GetApp().config
        loadPosition = config['stage'].getfloat('loadPosition')
        unloadPosition = config['stage'].getfloat('unloadPosition')

        currentZ=cockpit.interfaces.stageMover.getPosition()[2]
        if (currentZ < loadPosition):
            #move with the smalled possible mover
            moveZCheckMoverLimits(loadPosition)
            loaded=True
        else:
            #move with the smalled possible mover
            self.moveZCheckMoverLimits(unloadPosition)
            loaded=False
        self.setSampleStateText(loaded)


    #set sample state text and button state depending on if loaded or not.
    def setSampleStateText(self, loaded=False):
        if(loaded):
            self.sampleStateText.SetLabel('Loaded'.center(20))
            self.sampleStateText.SetBackgroundColour((255,0,0))
        else:
            self.sampleStateText.SetLabel('Unloaded'.center(20))
            self.sampleStateText.SetBackgroundColour((0,255,0))
        self.nameToButton['Load/Unload'].SetValue(loaded)


    ##Function to load/unload objective
    def changeObjective(self):
        # If we have only two objectives, then simply flip them
        h = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        if (h.numObjectives == 2):
            for obj in h.sortedObjectives:
                if h.currentObj != obj:
                    h.changeObjective(obj)
                    break
        else:
            # More than 2 objectives so need to present a list.
            menu = wx.Menu()
            for i, objective in enumerate(h.sortedObjectives):
                menu.Append(i, objective)
                menu.Bind(wx.EVT_MENU,
                          lambda evt, obj=objective: h.changeObjective(obj),
                          id=i)
            cockpit.gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    def textInfoField(self,title,onText,onColour,offText,offColour):
        textSizer=wx.BoxSizer(wx.VERTICAL)


    def cameraToggle(self,camera,i):
        camera.toggleState()
        self.wavelength=camera.wavelength
        self.color=camera.color
        isEnabled=camera.isEnabled
        if isEnabled is True:
            self.camButton[i].SetLabel("ON")
            self.SetBackgroundColour(ACTIVE_COLOR)
        elif isEnabled is False:
            self.camButton[i].SetLabel("OFF")
            self.SetBackgroundColour(INACTIVE_COLOR)


class LightToggleButton(SBitmapToggleButton):
    size = 75
    try:
        # wx >= 4
        _bmp = wx.Bitmap(size, size, depth=1)
    except:
        # wx < 4
        _bmp = wx.EmptyBitmap(size, size)
    _dc = wx.MemoryDC()
    _dc.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT,
                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False))
    _dc.SelectObject(_bmp)
    _dc.DrawCircle(size/2, size/2, size/3)
    _dc.SelectObject(wx.NullBitmap)
    mask = wx.Mask(_bmp)
    del _bmp


    def __init__(self, parent, light, **kwargs):
        size = (LightToggleButton.size, LightToggleButton.size)
        self.light = light
        if light.wavelength:
            label = str(int(light.wavelength))
            colour = cockpit.util.colors.wavelengthToColor(light.wavelength)
        else:
            label = light.name[0:4]
            colour = ((240,240,240))

        try:
            # wx >= 4
            bmpOff = wx.Bitmap(*size)
            bmpOn = wx.Bitmap(*size)
        except:
            # wx < 4
            bmpOff = wx.EmptyBitmap(*size)
            bmpOn = wx.EmptyBitmap(*size)

        bmpOff.SetMask(LightToggleButton.mask)
        bmpOn.SetMask(LightToggleButton.mask)

        dc = LightToggleButton._dc
        dc.SelectObject(bmpOff)
        dc.SetBackground(wx.Brush((192,192,192)))
        dc.Clear()
        tw, th = dc.GetTextExtent(label)
        dc.DrawText(label, (size[0]-tw)/2, (size[1]-th)/2)

        dc.SelectObject(bmpOn)
        dc.SetBackground(wx.Brush(colour))
        dc.Clear()
        dc.DrawText(label, (size[0] - tw) / 2, (size[1] - th) / 2)

        dc.SelectObject(wx.NullBitmap)

        kwargs['size'] = size
        super(LightToggleButton, self).__init__(parent, wx.ID_ANY, bmpOff, **kwargs)
        self.SetBitmapDisabled(bmpOff)
        self.SetBitmapSelected(bmpOn)
        self.Bind(wx.EVT_LEFT_DOWN, lambda evt: self.light.toggleState())
        from cockpit.gui import EvtEmitter, EVT_COCKPIT
        from cockpit.events import DEVICE_STATUS
        listener = EvtEmitter(self, DEVICE_STATUS)
        listener.Bind(EVT_COCKPIT, self.onStatusEvent)


    def onStatusEvent(self, evt):
        device, state = evt.EventData
        if device != self.light:
            return
        # Disable response to clicks while waiting for light state change.
        if state is STATES.enabling:
            self.Enable(False)
        else:
            self.Enable(True)

        toggle = state in [STATES.enabled, STATES.constant]

        self.SetToggle(toggle)
        wx.CallAfter(self.Refresh)



## Global window singleton.
TSwindow = None


def makeWindow(parent):
    global TSwindow
    TSwindow = TouchScreenWindow(parent, title = "Touch Screen view",
                                 style = wx.CAPTION| wx.RESIZE_BORDER |
                                 wx.MINIMIZE_BOX | wx.CLOSE_BOX)
    TSwindow.SetSize((1500,1000))
    # TODO - determine if we need to Show the touchscreen or not.
    # TODO - if the touchscreen is shown, ensure it is shown *on screen* ...
    # otherwise, it suddenly appears when raised on re-activating the app.
    #TSwindow.Show()
    #TSwindow.centerCanvas()


## Transfer a camera image to the mosaic.
def transferCameraImage():
    mosaic.transferCameraImage()

