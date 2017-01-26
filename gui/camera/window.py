
import wx

import depot
import events
import gui.keyboard
import util.userConfig
import gui.viewFileDropTarget
import viewPanel



## This class provides a grid of camera displays.
class CamerasWindow(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title = "Camera views",
                          style=wx.FRAME_TOOL_WINDOW | wx.CAPTION)
        
        self.numCameras = len(depot.getHandlersOfType(depot.CAMERA))

        self.panel = wx.Panel(self)

        # Make a 2xN grid of camera canvases, with menus above for selecting
        # which camera to use in that location.
        self.sizer = wx.FlexGridSizer(int(self.numCameras / 2.0 + .5), 2, 5, 5)
        ## List of ViewPanels we contain.
        self.views = []
        for i in xrange(self.numCameras):
            view = viewPanel.ViewPanel(self.panel)
            self.views.append(view)

        self.SetPosition((675, 280))

        events.subscribe("camera enable", self.onCameraEnableEvent)
        events.subscribe("image pixel info", self.onImagePixelInfo)
        events.subscribe('save exposure settings', self.onSaveSettings)
        events.subscribe('load exposure settings', self.onLoadSettings)
        gui.keyboard.setKeyboardHandlers(self)

        self.Bind(wx.EVT_CLOSE, self.onClose)

        self.resetGrid()
        self.SetDropTarget(gui.viewFileDropTarget.ViewFileDropTarget(self))


    ## The window is closed; use that as a proxy for closing the program,
    # even though we aren't the main window.
    def onClose(self, event):
        events.publish('program exit')
        event.Skip()


    ## Save our settings in the provided dict.
    def onSaveSettings(self, settings):
        settings['camera view window'] = []
        for view in self.views:
            if view.curCamera is not None:
                settings['camera view window'].append(view.curCamera.name)


    ## Load our settings from the provided dict.
    def onLoadSettings(self, settings):
        for view in self.views:
            view.disableCamera()
        for i, camName in enumerate(settings.get('camera view window', [])):
            camera = depot.getHandlerWithName(camName)
            self.views[i].enableCamera(camera)


    @util.threads.callInMainThread
    def onCameraEnableEvent(self, camera, enabled):
        activeViews = [view for view in self.views if view.getIsEnabled()]
        if enabled and camera not in [view.curCamera for view in activeViews]:
            inactiveViews = set(self.views).difference(activeViews)
            inactiveViews.pop().enable(camera)
        elif not(enabled):
            for view in activeViews:
                if view.curCamera is camera:
                    view.disable()
        self.resetGrid()


    ## When cameras are enabled/disabled, we resize the UI to suit. We want
    # there to always be at least one unused ViewPanel the user can use to 
    # enable a new camera, but ideally there should be as few as possible, 
    # to conserve screen real estate.
    def resetGrid(self):
        activeViews = []
        inactiveViews = []
        for view in self.views:
            view.Hide()
            if view.getIsEnabled():
                activeViews.append(view)
            else:
                inactiveViews.append(view)

        # Remake the sizer, adding all active views to it first.
        self.sizer.Clear()
        for view in activeViews:
            self.sizer.Add(view)
            view.Show()
        for view in inactiveViews:
            self.sizer.Add(view)
            if view is inactiveViews[0]:
                view.Show()
                # Other inactive views are hidden.
        self.sizer.Layout()
        self.panel.SetSizerAndFit(self.sizer)
        self.SetClientSize(self.panel.GetSize())


    ## Received information on the pixel under the mouse; update our title
    # to include that information.
    def onImagePixelInfo(self, coords, value):
        self.SetTitle("Camera views    (%d, %d): %d" % (coords[0], coords[1], value))


    ## Rescale each camera view.
    def rescaleViews(self):
        for view in self.views:
            if view.getIsEnabled():
                view.canvas.resetPixelScale()




## Global window singleton.
window = None

def makeWindow(parent):
    global window
    window = CamerasWindow(parent)
    window.Show()


## Simple passthrough.
def rescaleViews():
    window.rescaleViews()


## Retrieve the black- and white-points for a given camera's display.
def getCameraScaling(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getScaling()
    raise RuntimeError("Tried to get camera scalings for non-active camera [%s]" % camera.name)


## As above, but get the relative values used to generate the black/whitepoints.
def getRelativeCameraScaling(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getRelativeScaling()
    raise RuntimeError("Tried to get camera scalings for non-active camera [%s]" % camera.name)



## Retrieve the image currently displayed by the specified camera.
def getImageForCamera(camera):
    for view in window.views:
        if view.curCamera is camera:
            return view.getPixelData()
