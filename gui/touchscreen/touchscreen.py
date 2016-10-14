import collections
import FTGL
import numpy
from OpenGL.GL import *
import os
import scipy.ndimage.measurements
import threading
import time
import wx
import wx.lib.buttons as buttons
from wx.lib.agw.shapedbutton import SButton, SBitmapButton,SBitmapToggleButton,SToggleButton
from gui.toggleButton import ACTIVE_COLOR, INACTIVE_COLOR


import slavecanvas
import slaveOverview
import slaveMacroStageZ
import gui.macroStage.macroStageBase
import depot
import events
import gui.camera.window
import gui.dialogs.gridSitesDialog
import gui.dialogs.offsetSitesDialog
import gui.guiUtils
import gui.keyboard
import gui.mosaic.window
import interfaces.stageMover
import util.user
import util.threads
import util.userConfig
import math

from cockpit import COCKPIT_PATH
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



## This class handles the UI of the mosaic.
class TouchScreenWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)
        self.panel = wx.Panel(self)
        self.masterMosaic=gui.mosaic.window.MosaicWindow
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        ## Last known location of the mouse.
        self.prevMousePos = None
        ## Last click position of the mouse.
        self.lastClickPos = None
        ## Function to call when tiles are selected.
        self.selectTilesFunc = None
        ## True if we're generating a mosaic.
        self.amGeneratingMosaic = False
        ## get an objective handeler and list of all objectives. 
        self.objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.listObj = list(self.objective.nameToOffset.keys())
        ## Lock on generating mosaics.
        self.mosaicGenerationLock = threading.Lock()
        ## Boolean that indicates if the current mosaic generation thread
        # should exit.
        self.shouldEndOldMosaic = False
        ## Boolean that indicates if the current mosaic generation thread
        # should pause.
        self.shouldPauseMosaic = False

        ## Camera we last used for making a mosaic.
        self.prevMosaicCamera = None

        ## Mosaic tile overlap
        self.overlap = 0.0

        ## Size of the box to draw at the center of the crosshairs.
        self.crosshairBoxSize = 0
        ## Color to use when making new Site instances.
        self.siteColor = SITE_COLORS[0][1]
        ## Current selected sites for highlighting with crosshairs.
        self.selectedSites = set()

        ## Parameters defining the focal plane -- a tuple of
        # (point on plane, normal vector to plane).
        self.focalPlaneParams = None

        ## Font to use for site labels.
        self.font = FTGL.TextureFont(
                os.path.join(COCKPIT_PATH, 'resources',
                             'fonts', 'GeosansLight.ttf'))
        self.defaultFaceSize = 64
        self.font.FaceSize(self.defaultFaceSize)

        #default scale bar size is Zero
        self.scalebar = 0
        #Default to drawing primitives
        self.drawPrimitives = True
        ##define text strings to change status strings.
        self.sampleStateText=None
        ## Maps button names to wx.Button instances.
        self.nameToButton = {}
        self.nameToText={}
        self.bitmapsPath = os.path.join(COCKPIT_PATH, 'resources',
                             'bitmaps')

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
        objectiveSizer=wx.GridSizer(rows=2, cols=2)
        
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

        self.objectiveSelectedText=wx.StaticText(self.buttonPanel,-1,
                                                 style=wx.ALIGN_CENTER)
        self.objectiveSelectedText.SetFont(font)
        self.objectiveSelectedText.SetLabel(self.objective.curObjective.center(15))

        colour = depot.getHandlersOfType(depot.OBJECTIVE)[0].nameToColour.get(self.objective.curObjective)
        colour= (colour[0]*255,colour[1]*255,colour[2]*255)
        self.sampleStateText.SetBackgroundColour(colour)
        textSizer2.Add(self.objectiveSelectedText, 0, wx.CENTER|wx.ALL,border=5)

        objectiveSizer.Add(textSizer2, 0, wx.EXPAND|wx.ALL, border=5)
            
        ##mosaic control button panel
        mosaicButtonSizer=wx.GridSizer(rows=2, cols=2)

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
        
 
        # Find out light devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)
        lightToggles = sorted(lightToggles, key = lambda l: l.wavelength)
        laserSizer=wx.BoxSizer(wx.VERTICAL)
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT, wx.FONTWEIGHT_NORMAL,
                     wx.FONTSTYLE_NORMAL)
        for light in lightToggles:
            lineSizer=wx.BoxSizer(wx.HORIZONTAL)
            button = self.makeLaserToggleButton(self.buttonPanel, light.name,
                                     light,
                                     'laser_'+light.name+'-active.png',
                                     'laser_'+light.name+'-inactive.png',
                                     "enable/disable this light")
            lineSizer.Add(button, 0, wx.EXPAND|wx.ALL, border=2)
            laserPowerSizer=wx.BoxSizer(wx.VERTICAL)
            #To get powers we need to:
            lightHandlers=depot.getHandlersInGroup(light.groupName)
            laserPSizer=wx.BoxSizer(wx.HORIZONTAL)
            if len(lightHandlers) >1:
                #this is a laser and should have a power level
                for handler in depot.getHandlersInGroup(light.groupName):
                    if handler is not light:
                        powerHandler=handler
                #power down button, current power, power up button
                laserMinusButton=self.makeButton(self.buttonPanel,
                                                 light.name+'-10%',
                                     lambda myPowerHandler=powerHandler: self.decreaseLaserPower(myPowerHandler),
                                             None, 'minus.png',
                                             'Decrease laser power by 10%',
                                             size=(30,30))

                laserPowerText = wx.StaticText(self.buttonPanel,-1,
                                               style=wx.ALIGN_CENTER)
                laserPowerText.SetFont(font)
                #need to read actual power and then export the object in
                #self. so that we can change it at a later date
                label = '%5.1f %s'%(powerHandler.curPower,powerHandler.units)
                laserPowerText.SetLabel(label.rjust(10))
                self.nameToText[light.groupName+'power']=laserPowerText
                laserPlusButton=self.makeButton(self.buttonPanel,
                                                 light.name+'-10%',
                                    lambda myPowerHandler=powerHandler: self.increaseLaserPower(myPowerHandler),
                                             None, 'plus.png',
                                             'Increase laser power by 10%',
                                             size=(30,30))
                laserPSizer.Add(laserMinusButton,0, wx.EXPAND|wx.ALL)
                laserPSizer.Add(laserPowerText,0, wx.EXPAND|wx.ALL, border=3)
                laserPSizer.Add(laserPlusButton,0, wx.EXPAND|wx.ALL)
            else:
                #add and empty text box to keep sizing the same
                laserPowerText=wx.StaticText(self.buttonPanel,-1,
                                             style=wx.ALIGN_CENTER)
                laserPSizer.Add(laserPowerText, 0, wx.EXPAND|wx.ALL)
                
            laserPowerSizer.Add(laserPSizer, 0, wx.EXPAND|wx.ALL)
            #exposure times go with lights...
            #have minus button on left and plus button on right....
            laserExpSizer=wx.BoxSizer(wx.HORIZONTAL)
            laserMinusButton=self.makeButton(self.buttonPanel,light.name+'-10%',
                                    lambda mylight=light: self.decreaseLaserExp(mylight),
                                             None, 'minus.png',
                                             'Decrease exposure by 10%',
                                             size=(30,30))
            laserExpText = wx.StaticText(self.buttonPanel,-1,
                                               style=wx.ALIGN_CENTER)
            laserExpText.SetFont(font)
            #Read current exposure time and store pointer in 
            #self. so that we can change it at a later date
            label = '%5d ms'%(light.getExposureTime())
            laserExpText.SetLabel(label.rjust(10))
            self.nameToText[light.groupName+'exp']=laserExpText
            laserPlusButton=self.makeButton(self.buttonPanel,light.name+'+10%',
                                    lambda mylight=light: self.increaseLaserExp(mylight),
                                             None, 'plus.png',
                                             'Increase exposure by 10%',
                                             size=(30,30))


            laserExpSizer.Add(laserMinusButton,0, wx.EXPAND|wx.ALL)
            laserExpSizer.Add(laserExpText,0, wx.EXPAND|wx.ALL,border=3)
            laserExpSizer.Add(laserPlusButton,0, wx.EXPAND|wx.ALL)
            laserPowerSizer.Add(laserExpSizer, 0, wx.CENTRE|wx.ALL,border=2)
            lineSizer.Add(laserPowerSizer, 0, wx.EXPAND|wx.ALL,border=2)
            laserSizer.Add(lineSizer,0,wx.EXPAND|wx.ALL,border=2)
            
        cameraSizer=wx.GridSizer(cols=2)
        cameraVSizer=[None]*len(depot.getHandlersOfType(depot.CAMERA))
        self.camButton=[None]*len(depot.getHandlersOfType(depot.CAMERA))
        i=0
        for camera in depot.getHandlersOfType(depot.CAMERA):
            cameraVSizer[i] = wx.BoxSizer(wx.VERTICAL)
            # Remove the word 'camera' to shorten labels.
            name = camera.name.replace('camera', '').replace('  ', ' ')
            label = gui.device.Label(
                parent=self.buttonPanel, label=name)
            self.camButton[i] = gui.device.EnableButton(label='Off',
                                             parent=self.buttonPanel,
                                                        leftAction=camera.toggleState)
            camera.addListener(self.camButton[i])
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
        rightSideSizer.Add(laserSizer,0,wx.EXPAND)
        rightSideSizer.Add(wx.StaticLine(self.buttonPanel),
                           0, wx.ALL|wx.EXPAND, 5)
        rightSideSizer.Add(cameraSizer,0,wx.EXPAND)

        #run sizer fitting on button panel
        self.buttonPanel.SetSizerAndFit(rightSideSizer)        
        sizer.Add(self.buttonPanel, 1, wx.EXPAND,wx.RAISED_BORDER)

        limits = interfaces.stageMover.getHardLimits()[:2]
        ## start a slaveCanvas instance.
        self.canvas = slavecanvas.SlaveCanvas(self.panel, limits,
                                              self.drawOverlay,
                                              self.onMouse)
        sizer.Add(self.canvas, 3, wx.EXPAND)
        leftSizer= wx.BoxSizer(wx.VERTICAL)
        #add a macrostageXY overview section
        self.macroStageXY=slaveOverview.MacroStageXY(self.panel)
        leftSizer.Add(self.macroStageXY,3, wx.EXPAND)

        ##start a TSmacrostageZ instance
        self.macroStageZ=slaveMacroStageZ.slaveMacroStageZ(self.panel)
        leftSizer.Add(self.macroStageZ, 3,wx.EXPAND)

        ## Z control buttons
        zButtonSizer=wx.GridSizer(rows=3, cols=2)

        for args in [('Up', self.zMoveUp, None,
                      'up.png',
                      "Move up one Z step",(30,30)),
                     ('Inc Step', self.zIncStep, None,
                      'plus.png',
                      "Increase Z step",(30,30))]:
            button = self.makeButton(self.panel, *args)
            zButtonSizer.Add(button, 0, wx.EXPAND|wx.ALL,border=2)
        ##Text of position and step size
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        zPositionText = wx.StaticText(self.panel,-1,
                                      style=wx.ALIGN_CENTER)
        zPositionText.SetFont(font)
        #Read current exposure time and store pointer in 
        #self. so that we can change it at a later date
        label = 'Z Pos %5.2f'%(interfaces.stageMover.getPosition()[2])
        zPositionText.SetLabel(label.rjust(10))
        self.nameToText['Zpos']=zPositionText
        zButtonSizer.Add(zPositionText, 0, wx.EXPAND|wx.ALL,border=15)
        zStepText = wx.StaticText(self.panel,-1,
                                  style=wx.ALIGN_CENTER)
        zStepText.SetFont(font)
        #Read current exposure time and store pointer in 
        #self. so that we can change it at a later date
        label = 'Z Step %5d'%(interfaces.stageMover.getCurStepSizes()[2])
        zStepText.SetLabel(label.rjust(10))
        self.nameToText['ZStep']=zStepText
        zButtonSizer.Add(zStepText, 0, wx.EXPAND|wx.ALL,border=15)
        
        for args in [('Down', self.zMoveDown, None,
                      'down.png',
                      "Move down one Z step",(30,30)),
                     ('DecStep', self.zDecStep, None,
                      'minus.png',
                      "Decrease Z step",(30,30))]:
            button = self.makeButton(self.panel, *args)
            zButtonSizer.Add(button, 0, wx.EXPAND|wx.ALL,border=2)
        leftSizer.Add(zButtonSizer, 1,wx.EXPAND)


                     
        
        sizer.Add(leftSizer,1,wx.EXPAND)
        
        self.panel.SetSizerAndFit(sizer)
        self.SetRect((0, 0, 1800, 1000))

        events.subscribe('stage position', self.onAxisRefresh)
        events.subscribe('stage step size', self.onAxisRefresh)
        events.subscribe('soft safety limit', self.onAxisRefresh)
        events.subscribe('objective change', self.onObjectiveChange)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('user login', self.onLogin)
        events.subscribe('mosaic start', self.mosaicStart)
        events.subscribe('mosaic stop', self.mosaicStop)
        events.subscribe('mosaic update', self.mosaicUpdate)
        events.subscribe('light source enable', self.lightSourceEnable)
        events.subscribe('laser power update', self.laserPowerUpdate)
        events.subscribe('laser exposure update', self.laserExpUpdate)
        

        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        for item in [self, self.panel, self.canvas]:
            gui.keyboard.setKeyboardHandlers(item)


    ## Create a button with the appropriate properties.
    def makeButton(self, parent, label, leftAction, rightAction, bitmap,
                   helpText,size = (75,75)):
        bmp=wx.Bitmap(os.path.join( self.bitmapsPath, bitmap),
                      wx.BITMAP_TYPE_ANY)
        button = SBitmapButton(parent, -1, bitmap=bmp, size = size)
        button.SetToolTipString(helpText)
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button

    ## Create a button with the appropriate properties.
    def makeToggleButton(self, parent, label, leftAction, rightAction, bitmap,
                         bitmapSelected,helpText,size = (75, 75)):
        bmp=wx.Bitmap(os.path.join( self.bitmapsPath, bitmap),
                      wx.BITMAP_TYPE_ANY)
        button = SBitmapToggleButton(parent, -1, bitmap=bmp, size = size)
        bmpSelected=wx.Bitmap(os.path.join( self.bitmapsPath, bitmapSelected),
                      wx.BITMAP_TYPE_ANY)
        button.SetBitmapSelected(bmpSelected)

        button.SetToolTipString(helpText)
        #Note left action is called with true if down, false if up
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button

    def makeLaserToggleButton(self, parent, label, light,
                              bitmapActive, bitmapInactive, helpText,
                              size = (75, 75)):
        bmpActive=wx.Bitmap(os.path.join( self.bitmapsPath, bitmapActive),
                      wx.BITMAP_TYPE_ANY)
        bmpInactive=wx.Bitmap(os.path.join( self.bitmapsPath, bitmapInactive),
                              wx.BITMAP_TYPE_ANY)
        button = SBitmapToggleButton(parent, -1, bitmap=bmpInactive, size = size)
        button.SetBitmapSelected(bmpActive)
        button.SetToolTipString(helpText)
        #Note left action is called with true if down, false if up
        button.Bind(wx.EVT_BUTTON, lambda event: self.laserToggle(event,
                                                                  light, button))
        self.nameToButton[label] = button
        return button

    def snapImage(self):
        #check that we have a camera and light source
        cams=0
        lights=0
        for camera in depot.getHandlersOfType(depot.CAMERA):
            if camera.getIsEnabled():
                cams=cams+1
        for light in depot.getHandlersOfType(depot.LIGHT_TOGGLE):
            if light.getIsEnabled():
                lights=lights+1
        if (cams is 0) or (lights is 0):
            print "Snap needs a light and a camera to opperate"
            return
            
        #take the image
        events.executeAndWaitFor("new image %s" %
                                 (list(interfaces.imager.imager.activeCameras)[0].name),
                                 interfaces.imager.imager.takeImage, 
                                 shouldStopVideo = False)
        gui.mosaic.window.transferCameraImage()
        self.Refresh()

    def laserToggle(self, event, light, button):
        if event.GetIsDown():
            light.setEnabled(True)
            events.publish('light source enable', light, True)
        else:
            light.setEnabled(False)
            button.SetBackgroundColour(BACKGROUND_COLOUR)
            events.publish('light source enable', light, False)

    def lightSourceEnable(self, light, state):
        button=self.nameToButton[light.name]
        #need to set button active and chnage colour
        button.SetValue(state)
        #check to see if there is a power handler
        powerHandler=None
        for handler in depot.getHandlersInGroup(light.groupName):
            if handler is not light:
                powerHandler=handler
        #if there is a powerHandler set the colour of the active button
        if powerHandler:
            button.SetOwnBackgroundColour(powerHandler.color)
    
    def laserPowerUpdate(self, light):
        textString=self.nameToText[light.groupName+'power']
        label = '%5.1f %s'%(light.curPower, light.units)
        textString.SetLabel(label.rjust(10))
        if light.powerSetPoint and light.curPower:
            matched = 0.95*light.powerSetPoint < light.curPower < 1.05*light.powerSetPoint
        else:
            matched = False
        if matched:
            textString.SetBackgroundColour(light.color)
        else:
            textString.SetBackgroundColour(BACKGROUND_COLOUR)
        self.Refresh()

    #Update exposure time text on event.
    def laserExpUpdate(self):
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
        currentPower=powerHandler.curPower
        newPower=int(currentPower*0.9)
        powerHandler.setPower(newPower)

    #function called by plus expsoure time button
    def increaseLaserPower(self,powerHandler):
        currentPower=powerHandler.curPower
        newPower=int(currentPower*1.1)
        powerHandler.setPower(newPower)


        
    ## Now that we've been created, recenter the canvas.
    def centerCanvas(self, event = None):
        curPosition = interfaces.stageMover.getPosition()[:2]

        # Calculate the size of the box at the center of the crosshairs.
        # \todo Should we necessarily assume a 512x512 area here?
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.crosshairBoxSize = 512 * objective.getPixelSize()
        self.offset = objective.getOffset()
        scale= (1/objective.getPixelSize())*0.5
        self.canvas.zoomTo(-curPosition[0]+self.offset[0],
                           curPosition[1]-self.offset[1], scale)

    #Zbutton functions
    def zMoveUp(self):
        interfaces.stageMover.step((0,0,1))
    def zMoveDown(self):
        interfaces.stageMover.step((0,0,-1))
    def zIncStep(self):
        interfaces.stageMover.changeStepSize(1)
    def zDecStep(self):
        interfaces.stageMover.changeStepSize(-1)
    

    ## Resize our canvas.
    def onSize(self, event):
        size = self.GetClientSizeTuple()
        self.panel.SetSize(size)
        # Subtract off the pixels dedicated to the sidebar.
        self.canvas.setSize((size[0] - SIDEBAR_WIDTH, size[1]))


    ## User logged in, so we may well have changed size; adjust our zoom to
    # suit.
    def onLogin(self, *args):
        self.centerCanvas()
        self.scalebar=util.userConfig.getValue('mosaicScaleBar', isGlobal = False,
                                               default= 0)
        self.overlap=util.userConfig.getValue('mosaicTileOverlap', isGlobal=False,
                                               default = 0)
        self.drawPrimitives=util.userConfig.getValue('mosaicDrawPrimitives',
                                            isGlobal = False, default = True)

    ## Get updated about new stage position info or step size.
    # This requires redrawing the display, if the axis is the X or Y axes.
    def onAxisRefresh(self, axis, *args):
        if axis in [0, 1]:
            # Only care about the X and Y axes.
            wx.CallAfter(self.Refresh)
        if axis is 2:
            #Z axis updates
            posString=self.nameToText['Zpos']
            label = 'Z Pos %5.2f'%(interfaces.stageMover.getPosition()[2])
            posString.SetLabel(label.rjust(10))
            stepString=self.nameToText['ZStep']
            label = 'Z Step %5.2f'%(interfaces.stageMover.getCurStepSizes()[2])
            stepString.SetLabel(label.rjust(10))
            wx.CallAfter(self.Refresh)
            
    ## User changed the objective in use; resize our crosshair box to suit.
    def onObjectiveChange(self, name, pixelSize, transform, offset, **kwargs):
        self.crosshairBoxSize = 512 * pixelSize
        self.offset = offset
        self.objectiveSelectedText.SetLabel(name.center(15))
        colour = self.objective.nameToColour.get(name)
        colour= (colour[0]*255,colour[1]*255,colour[2]*255)
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
                if gui.mosaic.window.window.amGeneratingMosaic:
                    self.masterMosaic.onAbort(gui.mosaic.window.window)
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
                wx.EVT_MENU(self.panel, menuId,
                        lambda event, color = color: self.saveSite(color))
                menuId += 1
            menu.AppendSeparator()
            menu.Append(menuId, "Set mosaic tile overlap")
            wx.EVT_MENU(self.panel, menuId,
                        lambda event: self.setTileOverlap())
            menuId += 1
            menu.Append(menuId, "Toggle mosaic scale bar")
            wx.EVT_MENU(self.panel, menuId,
                        lambda event: self.togglescalebar())
            menuId += 1
            menu.Append(menuId, "Toggle draw primitives")
            wx.EVT_MENU(self.panel, menuId,
                        lambda event: self.toggleDrawPrimitives())

            gui.guiUtils.placeMenuAtMouse(self.panel, menu)

        self.prevMousePos = mousePos

        if self.selectTilesFunc is not None:
            # Need to draw the box the user is drawing.
            self.Refresh()

        # HACK: switch focus to the canvas away from our listbox, otherwise
        # it will seize all future scrolling events.
        if self.IsActive():
            self.canvas.SetFocus()


    ## Draw the overlay. This largely consists of a crosshairs indicating
    # the current stage position, and any sites the user has saved.
    def drawOverlay(self):
        for site in interfaces.stageMover.getAllSites():
            # Draw a crude circle.
            x, y = site.position[:2]
            x = -x
            # Set line width based on zoom factor.
            lineWidth = max(1, self.canvas.scale * 1.5)
            glLineWidth(lineWidth)
            glColor3f(*site.color)
            glBegin(GL_LINE_LOOP)
            for i in xrange(8):
                glVertex3f(x + site.size * numpy.cos(numpy.pi * i / 4.0),
                        y + site.size * numpy.sin(numpy.pi * i / 4.0), 0)
            glEnd()
            glLineWidth(1)

            glPushMatrix()
            glTranslatef(x, y, 0)
            # Scale the text with respect to the current zoom factor.
            fontScale = 3 / max(5.0, self.canvas.scale)
            glScalef(fontScale, fontScale, 1)
            self.font.Render(str(site.uniqueID))
            glPopMatrix()

        self.drawCrosshairs(interfaces.stageMover.getPosition()[:2], (1, 0, 0))

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
            self.drawCrosshairs(site.position[:2], (0, 0, 1), 10000)

        # Draw the soft and hard stage motion limits
        glEnable(GL_LINE_STIPPLE)
        glLineWidth(2)
        softSafeties = interfaces.stageMover.getSoftLimits()[:2]
        hardSafeties = interfaces.stageMover.getHardLimits()[:2]
        for safeties, color, stipple in [(softSafeties, (0, 1, 0), 0x5555),
                                         (hardSafeties, (0, 0, 1), 0xAAAA)]:
            x1, x2 = safeties[0]
            y1, y2 = safeties[1]
            if hasattr (self, 'offset'):
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
            scalebarPos = [30,-10]

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
            glLineWidth(8)
            glBegin(GL_LINES)
            glVertex2f(x1,y1)
            glVertex2f(x2,y1)
            glEnd()
            glLineWidth(1)
	        # The scale label.
            self.font.FaceSize(16)
            glPushMatrix()
            labelPosX= x1
            labelPosY= y1 - (20/self.canvas.scale)
            glTranslatef(labelPosX, labelPosY, 0)
            fontScale = 1 / self.canvas.scale
            glScalef(fontScale, fontScale, 1)
            self.font.Render('%g um' % self.scalebar)
            glPopMatrix()

            # Restore the default font size.
            self.font.FaceSize(self.defaultFaceSize)
        #Draw stage primitives.
        if(self.drawPrimitives):
            # Draw device-specific primitives.
            glEnable(GL_LINE_STIPPLE)
            glLineStipple(1, 0xAAAA)
            glColor3f(0.4, 0.4, 0.4)
            primitives = interfaces.stageMover.getPrimitives()
            for p in primitives:
                if p.type in ['c', 'C']:
                    # circle: x0, y0, radius
                    self.drawScaledCircle(p.data[0], p.data[1],
                                          p.data[2], CIRCLE_SEGMENTS,
                                          offset=False)
                if p.type in ['r', 'R']:
                    # rectangle: x0, y0, width, height
                    self.drawScaledRectangle(*p.data, offset=False)
            glDisable(GL_LINE_STIPPLE)

    def drawScaledCircle(self, x0, y0, r, n, offset=True):
        dTheta = 2. * PI / n
        cosTheta = numpy.cos(dTheta)
        sinTheta = numpy.sin(dTheta)
        if offset:
            x0=x0-self.offset[0]
            y0 =y0+self.offset[1]
        x = r
        y = 0.

        glBegin(GL_LINE_LOOP)
        for i in xrange(n):
            glVertex2f(-(x0 + x), y0 + y)
            xOld = x
            x = cosTheta * x - sinTheta * y
            y = sinTheta * xOld + cosTheta * y
        glEnd()
		
    ## Draw a rectangle centred on x0, y0 of width w and height h.
    def drawScaledRectangle(self, x0, y0, w, h, offset=True):
        dw = w / 2.
        dh = h / 2.
        if offset:
            x0 = x0-self.offset[0]
            y0 = y0+self.offset[1]
        ps = [(x0-dw, y0-dh),
              (x0+dw, y0-dh),
              (x0+dw, y0+dh),
              (x0-dw, y0+dh)]

        glBegin(GL_LINE_LOOP)
        for i in xrange(-1, 4):
            glVertex2f(-ps[i][0], ps[i][1])
        glEnd()
    # Draw a crosshairs at the specified position with the specified color.
    # By default make the size of the crosshairs be really big.
    def drawCrosshairs(self, position, color, size = None):
        xSize = ySize = size
        if size is None:
            xSize = ySize = 100000
        x, y = position
        #if no offset defined we can't apply it!
        if hasattr(self, 'offset'):
            x = x-self.offset[0]
            y = y-self.offset[1]

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
        for i, j in [(-1, -1), (-1, 1), (1, 1), (1, -1)]:
            glVertex2d(-x + i * self.crosshairBoxSize / 2,
                    y + j * self.crosshairBoxSize / 2)
        glEnd()


    ## Display dialogue box to set tile overlap.
    def setTileOverlap(self):
        value = gui.dialogs.getNumberDialog.getNumberFromUser(
                    self.GetParent(),
                    "Set mosiac tile overlap.",
                    "Tile overlap in %",
                    self.overlap,
                    atMouse=True)
        self.overlap = float(value)
        util.userConfig.setValue('mosaicTileOverlap', self.overlap, isGlobal=False)



    ## Transfer an image from the active camera (or first camera) to the
    # mosaic at the current stage position.
    def transferCameraImage(self):
        gui.mosaic.window.transferCameraImage()
        self.Refresh()

    def togglescalebar(self):
        #toggle the scale bar between 0 and 1.
        if (self.scalebar!=0):
            self.scalebar = 0
        else:
            self.scalebar = 1
        #store current state for future.
        util.userConfig.setValue('mosaicScaleBar',self.scalebar, isGlobal=False)
        self.Refresh()

    def toggleDrawPrimitives(self):
        #toggle the scale bar between 0 and 1.
        if (self.drawPrimitives!=False):
            self.drawPrimitives=False
        else:
            self.drawPrimitives = True
        #store current state for future.
        util.userConfig.setValue('mosaicDrawPrimitives',self.drawPrimitives,
                                 isGlobal=False)
        self.Refresh()


    ## call main mosaic function and refresh
    def saveSite(self, color = None):
        self.masterMosaic.saveSite(gui.mosaic.window.window, color)
        self.Refresh()


    ## Set the site marker color.
    def setSiteColor(self, color):
        self.masterMosaic.setSiteColor(gui.mosaic.window.window, color)

    ## Display a menu that allows the user to control the appearance of
    # the markers used to mark sites.
    def displaySiteMakerMenu(self, event = None):
        menu = wx.Menu()
        for i, (label, color) in enumerate(SITE_COLORS):
            menu.Append(i + 1, "Mark sites in %s" % label)
            wx.EVT_MENU(self.panel, i + 1,
                    lambda event, color = color: self.setSiteColor(color))
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


    # ## Calculate the focal plane of the sample.
    # def setFocalPlane(self, event = None):
    #     sites = self.getSelectedSites()
    #     positions = [s.position for s in sites]
    #     if len(positions) < 3:
    #         wx.MessageDialog(self,
    #                 "Please select at least 3 in-focus sites.",
    #                 "Insufficient input.").ShowModal()
    #         return
    #     positions = numpy.array(positions)
    #     # Pick a point in the plane, as the average of all site positions.
    #     center = positions.mean(axis = 0)
    #     # Try every combinations of points, and average their resulting normal
    #     # vectors together.
    #     normals = []
    #     for i in xrange(len(positions)):
    #         p1 = positions[i] - center
    #         for j in xrange(i + 1, len(positions)):
    #             p2 = positions[j] - center
    #             for k in xrange(j + 1, len(positions)):
    #                 p3 = positions[k] - center
    #                 points = numpy.rot90([p1, p2, p3])
    #                 # Calculate normal vector, and normalize
    #                 normal = numpy.cross(p2 - p1, p3 - p1)
    #                 magnitude = numpy.sqrt(sum(normal * normal))
    #                 normals.append(normal / magnitude)

    #     # Ensure all normals point in the same direction. If they oppose,
    #     # their sum should be ~0; if they are aligned, it should be
    #     # ~2.
    #     normals = numpy.array(normals)
    #     base = normals[0]
    #     for normal in normals[1:]:
    #         if sum(base + normal) < .5:
    #             # Opposed normals.
    #             normal *= -1
    #     self.focalPlaneParams = (center, normals.mean(axis = 0))
    #     deltas = []
    #     for site in sites:
    #         pos = numpy.array(site.position)
    #         z = self.getFocusZ(pos)
    #         deltas.append(pos[2] - z)
    #         print "Delta for",pos,"is",(pos[2] - z)
    #     print "Average delta is",numpy.mean(deltas),"with std",numpy.std(deltas)


    # ## Clear the focal plane settings.
    # def clearFocalPlane(self):
    #     self.focalPlaneParams = None


    ## Go to the specified XY position. If we have a focus plane defined,
    # go to the appropriate Z position to maintain focus.
    def goTo(self, target, shouldBlock = False):
        if self.focalPlaneParams:
            targetZ = self.getFocusZ(target)
            interfaces.stageMover.goTo((target[0], target[1], targetZ),
                    shouldBlock)
        else:
            #IMD 20150306 Save current mover, change to coarse to generate mosaic
			# do move, and change mover back.
            originalMover= interfaces.stageMover.mover.curHandlerIndex
            interfaces.stageMover.mover.curHandlerIndex = 0
            interfaces.stageMover.goToXY(target, shouldBlock)
            interfaces.stageMover.mover.curHandlerIndex = originalMover

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
            self.selectedSites.add(interfaces.stageMover.getSite(siteID))
        self.Refresh()


    ## User double-clicked on a site in the sites box; go to that site.
    # \todo Enforcing int site IDs here.
    def onDoubleClickSite(self, event):
        item = event.GetString()
        siteID = int(item.split(':')[0])
        interfaces.stageMover.goToSite(siteID)


    ## Return a list of of the currently-selected Sites.
    def getSelectedSites(self):
        result = []
        for item in self.sitesBox.GetSelections()[::-1]:
            text = self.sitesBox.GetString(item)
            siteID = int(text.split(':')[0])
            result.append(interfaces.stageMover.getSite(siteID))
        return result





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

    ##Wrapper functions to call the main mosaic window version
    def displayMosaicMenu(self):
        self.masterMosaic.displayMosaicMenu(gui.mosaic.window.window)

    def continueMosaic(self):
        self.masterMosaic.continueMosaic(gui.mosaic.window.window)


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
        if not gui.guiUtils.getUserPermission(
                "Are you sure you want to delete every tile in the mosaic?",
                "Delete confirmation"):
            return
        self.canvas.deleteAll()


    ## Rescale each tile according to that tile's own values.
    def autoscaleTiles(self, event = None):
        self.canvas.rescale(None)


    ## Let the user select a camera to use to rescale the tiles.
    def displayRescaleMenu(self, event = None):
        self.showCameraMenu("Rescale according to %s camera",
                self.rescaleWithCamera)


    ## Given a camera handler, rescale the mosaic tiles based on that
    # camera's display's black- and white-points.
    def rescaleWithCamera(self, camera):
        self.canvas.rescale(gui.camera.window.getCameraScaling(camera))

    ##Function to load/unload objective
    def loadUnload(self):
        #toggle to load or unload the sample
        configurator = depot.getHandlersOfType(depot.CONFIGURATOR)[0]
        currentZ=interfaces.stageMover.getPosition()[2]         

        if (configurator.getValue('loadPosition') and
            configurator.getValue('unloadPosition')):
            loadPosition=configurator.getValue('loadPosition')
            unloadPosition=configurator.getValue('unloadPosition')
            if (currentZ < loadPosition):
                #move with the smalled possible mover
                self.moveZCheckMoverLimits(loadPosition)
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
            
  
    def moveZCheckMoverLimits(self, target):
        #Need to check current mover limits, see if we exceed them and if
        #so drop down to lower mover handler.
        originalMover= interfaces.stageMover.mover.curHandlerIndex
        limits = interfaces.stageMover.getIndividualSoftLimits(2)
        currentPos= interfaces.stageMover.getPosition()[2]
        offset = target - currentPos
        doneMove=False
        while (interfaces.stageMover.mover.curHandlerIndex >= 0):
            if ((currentPos + offset)<
                limits[interfaces.stageMover.mover.curHandlerIndex][1] and
                (currentPos + offset) >
                limits[interfaces.stageMover.mover.curHandlerIndex][0]):

                #Can do it with this mover...
                interfaces.stageMover.goToZ(target)
                interfaces.stageMover.mover.curHandlerIndex = originalMover
                doneMove=True
                break
            else: 
                interfaces.stageMover.mover.curHandlerIndex -= 1

        if not doneMove:
            print "cannot load/unload move too large for any Z axis!"
        #retrun to original active mover.
        interfaces.stageMover.mover.curHandlerIndex = originalMover


        
    ##Function to load/unload objective
    def changeObjective(self):
        #if we have only two objectioves, then simply flip them
        currentObj=self.objective.curObjective
        if (len(self.listObj) == 2):
            for obj in self.listObj:
                if currentObj != obj:
                    self.objective.changeObjective(obj)
        else:
            #more than 2 objectives so need to present a list
            showObjectiveMenu()
        
        

    def showObjectiveMenu(self):
        i=0
        menu = wx.Menu()
        for objective in self.listObj:
            menu.Append(i + 1, objective)
            wx.EVT_MENU(self.panel, i + 1,
                        lambda event,
                        objective:self.objective.changeObjective(objective))
            gui.guiUtils.placeMenuAtMouse(self.panel, menu)

    ## Handle the user clicking the abort button.
    def onAbort(self, *args):
        if self.amGeneratingMosaic:
            self.shouldPauseMosaic = True
        self.nameToButton['Run mosaic'].SetLabel('Run mosaic')
        # Stop deleting tiles, while we're at it.
        self.onDeleteTiles(shouldForceStop = True)

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
            
        

## Global window singleton.
TSwindow = None


def makeWindow(parent):
    global TSwindow
    TSwindow = TouchScreenWindow(parent, title = "Touch Screen view",
                                 style = wx.CAPTION| wx.RESIZE_BORDER |
                                 wx.MINIMIZE_BOX | wx.CLOSE_BOX)
    TSwindow.SetSize((1500,1000))
    TSwindow.Show()
    TSwindow.centerCanvas()


## Transfer a camera image to the mosaic.
def transferCameraImage():
    gui.mosaic.window.transferCameraImage()

