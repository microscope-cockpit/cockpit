import numpy
import time
import traceback
import wx

import depot
import events
import gui.guiUtils
import gui.imageViewer.viewCanvas
import interfaces.stageMover
import interfaces.imager
import util.logger

## Default viewer dimensions.
(VIEW_WIDTH, VIEW_HEIGHT) = (512, 552)

def maintainVideoMode(function):
    def wrappedFunc(*args, **kwargs):
        # Need to ensure video mode is disabled.
        wasInVideoMode = interfaces.imager.isVideoRunning()
        if wasInVideoMode:
            interfaces.imager.stopVideo()
            while interfaces.imager.isVideoRunning():
                time.sleep(0.1)
        result = function(*args, **kwargs)
        # Re-enable video mode
        if wasInVideoMode:
            interfaces.imager.videoMode()
        return result
    return wrappedFunc

## This class provides an interface for a single camera. It includes a
# button at the top to select which camera to use, a viewing area to display
# the image the camera sees, and a histogram at the bottom.
class ViewPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)

        ## Handle of the current camera we're controlling.
        self.curCamera = None

        columnSizer = wx.BoxSizer(wx.VERTICAL)
        ## Clickable text box showing the name of the currently-selected
        # camera.
        self.selector = wx.StaticText(self,
                style = wx.RAISED_BORDER | wx.ALIGN_CENTRE | wx.ST_NO_AUTORESIZE, 
                size = (VIEW_WIDTH, 30))
        self.selector.Bind(wx.EVT_LEFT_DOWN, self.onSelector)

        columnSizer.Add(self.selector, 0)

        ## Panel for holding our canvas.
        self.canvasPanel = wx.Panel(self)
        self.canvasPanel.SetMinSize((VIEW_WIDTH, VIEW_HEIGHT))
        columnSizer.Add(self.canvasPanel)

        self.SetSizerAndFit(columnSizer)

        ## Canvas we paint the camera's view onto. Created when we connect a
        # camera, and destroyed after.
        self.canvas = None

        self.disableCamera()
        # We need to respond to this event after the cameras do, since we
        # need them to have gotten their new names.
        events.subscribe("drawer change", self.onDrawerChange, priority = 1000)
        self.SetDoubleBuffered(True)


    ## User interacted with our current image; on double-clicks we center
    # the display on the mouse.
    def onMouse(self, event):
        if event.LeftDClick():
            x, y = event.GetPosition()
            sizeX, sizeY = self.canvas.GetSize()
            sizeY -= gui.imageViewer.viewCanvas.HISTOGRAM_HEIGHT
            pixelSize = depot.getHandlersOfType(depot.OBJECTIVE)[0].getPixelSize()
            dx = ((sizeX / 2) - x) * pixelSize
            dy = ((sizeY / 2) - y) * pixelSize
            #Need to see if the current movers have xy capbility
            positions = interfaces.stageMover.getAllPositions()
            handler = interfaces.stageMover.mover.curHandlerIndex
            if ((positions[handler][0] == None) or ( positions[handler][1] == None)):
                #We dont have an x or y axis so use the main handler
                originalMover= interfaces.stageMover.mover.curHandlerIndex
                interfaces.stageMover.mover.curHandlerIndex = 0
                interfaces.stageMover.moveRelative((dx, dy, 0))
                interfaces.stageMover.mover.curHandlerIndex = originalMover
            else:
               interfaces.stageMover.moveRelative((dx, dy, 0))


    ## User clicked on the selector. Pop up a menu to let them either activate
    # a camera or, if we're already activated, deactivate the current one.
    # We also let them set the camera's readout size here, if a camera is
    # active.
    def onSelector(self, event):
        menu = wx.Menu()
        if self.curCamera is not None:
            item = menu.Append(-1, "Disable %s" % self.curCamera.descriptiveName)
            self.Bind(wx.EVT_MENU, self.disableCamera, item)
            menu.InsertSeparator(1)
            items = self.canvas.getMenuActions()
            for label, action in items:
                item = menu.Append(-1, label)
                self.Bind(wx.EVT_MENU,
                        lambda event, action = action: action(), item)
            menu.InsertSeparator(len(items) + 2)
            for size in self.curCamera.getImageSizes():
                item = menu.Append(-1, "Set image size to %s" % str(size))
                self.Bind(wx.EVT_MENU,
                        lambda event, size = size: self.curCamera.setImageSize(size),
                        item)                
        else:
            # Get all inactive cameras.
            cameras = depot.getHandlersOfType(depot.CAMERA)
            cameras.sort(key = lambda c: c.descriptiveName)
            for camera in cameras:
                if not camera.getIsEnabled():
                    item = menu.Append(-1, "Enable %s" % camera.descriptiveName)
                    self.Bind(wx.EVT_MENU, 
                            lambda event, camera = camera: self.enableCamera(camera),
                            item)
        gui.guiUtils.placeMenuAtMouse(self, menu)


    ## Deactivate our current camera.
    @maintainVideoMode
    def disableCamera(self, event = None):
        self.selector.SetLabel("No camera")
        self.selector.SetBackgroundColour((180, 180, 180))
        self.selector.Refresh()
        if self.curCamera is not None:
            # Wrap this in a try/catch since it will fail if the initial
            # camera enabling failed.
            try:
                events.unsubscribe("new image %s" % self.curCamera.name, self.onImage)
                self.curCamera.setEnabled(False)
            except Exception, e:
                util.logger.log.error("Error disabling camera: %s", e)
                util.logger.log.error(traceback.format_exc())
            events.publish('camera enable', self.curCamera, False)
            self.curCamera = None
            self.canvas.clear()
        if self.canvas is not None:
            # Destroy the canvas.
            self.canvas.clear(shouldDestroy = True)
            self.canvas = None


    ## Enable the specified camera.
    # Need to disable video mode to prevent errors that seem to be due
    # to updating a canvas before it has been created and sized.
    @maintainVideoMode
    def enableCamera(self, camera):
        self.selector.SetLabel(camera.descriptiveName)
        self.selector.SetBackgroundColour(camera.color)
        self.selector.Refresh()
        self.curCamera = camera
        self.curCamera.setEnabled(True)
        events.publish('camera enable', self.curCamera, True)

        # NB the 512 here is the largest texture size our graphics card can
        # gracefully handle.
        self.canvas = gui.imageViewer.viewCanvas.ViewCanvas(self.canvasPanel,
                512, size = (VIEW_WIDTH, VIEW_HEIGHT),
                mouseHandler = self.onMouse)
        self.canvas.SetSize((VIEW_WIDTH, VIEW_HEIGHT))
        self.canvas.resetView()

        # Subscribe to new image events only after canvas is prepared.
        events.subscribe("new image %s" % self.curCamera.name, self.onImage)

    ## React to the drawer changing, by updating our labels and colors.
    def onDrawerChange(self, drawerHandler):
        if self.getIsEnabled():
            self.selector.SetLabel(self.curCamera.descriptiveName)
            color = drawerHandler.getColorForCamera(self.curCamera.name)
            self.selector.SetBackgroundColour(color)
            self.Refresh()


    ## Receive a new image and send it to our canvas.
    def onImage(self, data, *args):
        self.canvas.setImage(data)


    ## Return True if we currently display a camera.
    def getIsEnabled(self):
        return self.curCamera is not None and self.curCamera.getIsEnabled()


    ## Get the black- and white-point for the view.
    def getScaling(self):
        return self.canvas.getScaling()


    ## As above, but the relative values used to generate them instead.
    def getRelativeScaling(self):
        return self.canvas.getRelativeScaling()


    ## Get the current pixel data for the view.
    def getPixelData(self):
        return self.canvas.imageData


    ## Debugging: convert to string.
    def __repr__(self):
        descString = ", disabled"
        if self.curCamera is not None:
            descString = "for %s" % self.curCamera.name
        return "<Camera ViewPanel %s>" % descString
