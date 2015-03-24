import collections
import FTGL
import numpy
from OpenGL.GL import *
import os
import scipy.ndimage.measurements
import threading
import time
import wx

import canvas
import depot
import events
import gui.camera.window
import gui.dialogs.gridSitesDialog
import gui.dialogs.offsetSitesDialog
import gui.guiUtils
import gui.keyboard
import interfaces.stageMover
import util.user
import util.threads

## Size of the crosshairs indicating the stage position.
CROSSHAIR_SIZE = 10000
## Valid colors to use for site markers.
SITE_COLORS = [('green', (0, 1, 0)), ('red', (1, 0, 0)),
    ('blue', (0, 0, 1)), ('orange', (1, .6, 0))]

## Width of widgets in the sidebar.
SIDEBAR_WIDTH = 150

## Simple structure for marking potential beads.
BeadSite = collections.namedtuple('BeadSite', ['pos', 'size', 'intensity'])



## This class handles the UI of the mosaic. 
class MosaicWindow(wx.Frame):
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)
        self.panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        ## Last known location of the mouse.
        self.prevMousePos = None
        ## Last click position of the mouse.
        self.lastClickPos = None
        ## Function to call when tiles are selected. 
        self.selectTilesFunc = None
        ## True if we should stop what we're doing.
        self.shouldAbort = False
        ## True if we're generating a mosaic.
        self.amGeneratingMosaic = False

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
                os.path.join('resources', 'fonts', 'GeosansLight.ttf'))
        self.font.FaceSize(64)

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
            button = self.makeButton(self.panel, *args)
            sideSizer.Add(button, 0, wx.EXPAND)
        
        ## Panel for controls dealing with specific sites.
        self.sitesPanel = wx.Panel(self.panel, style = wx.BORDER_SUNKEN)
        sitesSizer = wx.BoxSizer(wx.VERTICAL)
        ## Holds a list of sites.
        self.sitesBox = wx.ListBox(self.sitesPanel,
                style = wx.LB_EXTENDED | wx.LB_SORT, size = (SIDEBAR_WIDTH, -1))
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
                 lambda *args: gui.dialogs.gridSitesDialog.showDialog(self),
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
            button = self.makeButton(self.sitesPanel, *args,
                    size = (SIDEBAR_WIDTH, -1))
            sitesSizer.Add(button)
        
        self.sitesPanel.SetSizerAndFit(sitesSizer)
        sideSizer.Add(self.sitesPanel, 1)
        sizer.Add(sideSizer, 0, wx.EXPAND)

        limits = interfaces.stageMover.getHardLimits()[:2]
        ## MosaicCanvas instance.
        self.canvas = canvas.MosaicCanvas(self.panel, limits, self.drawOverlay, 
                self.onMouse)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        self.panel.SetSizerAndFit(sizer)
        self.SetRect((1280, 456, 878, 560))

        events.subscribe('stage position', self.onAxisRefresh)
        events.subscribe('stage step size', self.onAxisRefresh)
        events.subscribe('soft safety limit', self.onAxisRefresh)
        events.subscribe('objective change', self.onObjectiveChange)
        events.subscribe('user abort', self.onAbort)
        events.subscribe('user login', self.onLogin)

        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.onMouse)
        for item in [self, self.panel, self.canvas, self.sitesPanel]:
            gui.keyboard.setKeyboardHandlers(item)


    ## Create a button with the appropriate properties.
    def makeButton(self, parent, label, leftAction, rightAction, helpText,
            size = (-1, -1)):
        button = wx.Button(parent, -1, label, size = size)
        button.SetToolTipString(helpText)
        button.Bind(wx.EVT_BUTTON, lambda event: leftAction())
        if rightAction is not None:
            button.Bind(wx.EVT_RIGHT_DOWN, lambda event: rightAction())
        self.nameToButton[label] = button
        return button


    ## Now that we've been created, recenter the canvas.
    def centerCanvas(self, event = None):
        curPosition = interfaces.stageMover.getPosition()[:2]
        self.canvas.zoomTo(-curPosition[0], curPosition[1], 1)
        # Calculate the size of the box at the center of the crosshairs. 
        # \todo Should we necessarily assume a 512x512 area here?
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        self.crosshairBoxSize = 512 * objective.getPixelSize()


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


    ## Get updated about new stage position info or step size.
    # This requires redrawing the display, if the axis is the X or Y axes.
    def onAxisRefresh(self, axis, *args):
        if axis in [0, 1]:
            # Only care about the X and Y axes.
            wx.CallAfter(self.Refresh)


    ## User changed the objective in use; resize our crosshair box to suit.
    def onObjectiveChange(self, name, pixelSize, transform):
        self.crosshairBoxSize = 512 * pixelSize


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
                target = self.canvas.mapScreenToCanvas(mousePos)
                self.goTo(target)
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


    # Draw a crosshairs at the specified position with the specified color.
    # By default make the size of the crosshairs be really big.
    def drawCrosshairs(self, position, color, size = None):
        xSize = ySize = size
        if size is None:
            xSize = ySize = 100000
        x, y = position

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


    ## This generator function creates a clockwise spiral pattern.
    def mosaicStepper(self):
        directions = [(0, -1), (-1, 0), (0, 1), (1, 0)]
        curDirection = 0
        curSpiralSize = 1
        lastX = lastY = 0
        i = 0
        while True:
            dx, dy = directions[i % 4]
            for j in xrange(1, curSpiralSize + 1):
                yield (lastX + dx * j, lastY + dy * j)
            lastX += dx * curSpiralSize
            lastY += dy * curSpiralSize
            if i % 2:
                curSpiralSize += 1
            i += 1


    ## Move the stage in a spiral pattern, stopping to take images at regular
    # intervals, to generate a stitched-together high-level view of the stage
    # contents. Check for an existing paused mosaic function and destroy it
    # if it exists.
    # \param camera Handler of the camera we're collecting images from.
    @util.threads.callInNewThread
    def generateMosaic(self, camera):
        if self.shouldPauseMosaic:
            # We have a paused mosaic that needs to be destroyed.
            self.shouldEndOldMosaic = True
        self.generateMosaic2(camera)


    def generateMosaic2(self, camera):
        # Acquire the mosaic lock so no other mosaics can run.
        self.mosaicGenerationLock.acquire()
        
        self.amGeneratingMosaic = True
        self.nameToButton['Run mosaic'].SetLabel('Stop mosaic')
        self.prevMosaicCamera = camera
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        width, height = camera.getImageSize()
        width *= objective.getPixelSize()
        height *= objective.getPixelSize()
        centerX, centerY, curZ = interfaces.stageMover.getPosition()
        prevPosition = (centerX, centerY)
        for dx, dy in self.mosaicStepper():
            while self.shouldPauseMosaic:
                # Wait until the mosaic is unpaused.
                if self.shouldEndOldMosaic:
                    # End the mosaic.
                    self.shouldEndOldMosaic = False
                    self.shouldPauseMosaic = False
                    self.amGeneratingMosaic = False
                    self.mosaicGenerationLock.release()
                    return
                time.sleep(.1)
            # Take an image.
            data, timestamp = events.executeAndWaitFor(
                    "new image %s" % camera.name, 
                    interfaces.imager.takeImage, shouldBlock = True)
            # Get the scaling for the camera we're using, since they may
            # have changed. Calculate them manually since the camera's
            # image display may be changing rapidly and its absolute black/
            # whitepoints may not be accurate for the image we're working with.
            black, white = gui.camera.window.getRelativeCameraScaling(camera)
            minVal = data.min()
            maxVal = data.max()
            scaleMin = black * (maxVal - minVal) + minVal
            scaleMax = white * (maxVal - minVal) + minVal
            events.executeAndWaitFor('mosaic canvas paint', 
                    self.canvas.addImage, data, 
                    (-prevPosition[0] - width / 2, 
                        prevPosition[1] - height / 2, curZ),
                    (width, height), scalings = (scaleMin, scaleMax),
                    shouldRefresh = True)
            # Move to the next position.
            target = (centerX + dx * width, centerY + dy * height)
            self.goTo(target, True)
            prevPosition = target
            curZ = interfaces.stageMover.getPositionForAxis(2)

        # We should never reach this point!
        self.mosaicGenerationLock.release()


    ## Transfer an image from the active camera (or first camera) to the
    # mosaic at the current stage position.
    def transferCameraImage(self):
        camera = self.prevMosaicCamera
        if camera is None or not camera.getIsEnabled():
            # Select the first active camera.
            for cam in depot.getHandlersOfType(depot.CAMERA):
                if cam.getIsEnabled():
                    camera = cam
                    break
        # Get image size in microns.
        objective = depot.getHandlersOfType(depot.OBJECTIVE)[0]
        width, height = camera.getImageSize()
        width *= objective.getPixelSize()
        height *= objective.getPixelSize()
        x, y, z = interfaces.stageMover.getPosition()
        data = gui.camera.window.getImageForCamera(camera)
        self.canvas.addImage(data, (-x - width / 2, y - height / 2, z),
                (width, height),
                scalings = gui.camera.window.getCameraScaling(camera))
        self.Refresh()


    ## Save the current stage position as a new site with the specified
    # color (or our currently-selected color if none is provided).
    def saveSite(self, color = None):
        if color is None:
            color = self.siteColor
        position = interfaces.stageMover.getPosition()
        interfaces.stageMover.saveSite(
                interfaces.stageMover.Site(position, None, color,
                        size = self.crosshairBoxSize))
        self.Refresh()


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
            wx.EVT_MENU(self.panel, i + 1,
                    lambda event, color = color: self.setSiteColor(color))
        gui.guiUtils.placeMenuAtMouse(self.panel, menu)


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
        for i in xrange(len(positions)):
            p1 = positions[i] - center
            for j in xrange(i + 1, len(positions)):
                p2 = positions[j] - center
                for k in xrange(j + 1, len(positions)):
                    p3 = positions[k] - center
                    points = numpy.rot90([p1, p2, p3])
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
            print "Delta for",pos,"is",(pos[2] - z)
        print "Average delta is",numpy.mean(deltas),"with std",numpy.std(deltas)


    ## Clear the focal plane settings.
    def clearFocalPlane(self):
        self.focalPlaneParams = None


    ## Go to the specified XY position. If we have a focus plane defined, 
    # go to the appropriate Z position to maintain focus.
    def goTo(self, target, shouldBlock = False):
        if self.focalPlaneParams:
            targetZ = self.getFocusZ(target)
            interfaces.stageMover.goTo((target[0], target[1], targetZ), 
                    shouldBlock)
        else:
            interfaces.stageMover.goToXY(target, shouldBlock)


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


    ## Delete the sites the user has selected in our sitebox.
    def deleteSelectedSites(self, event = None):
        # Go in reverse order so that removing items from the box doesn't
        # invalidate future indices.
        for item in self.sitesBox.GetSelections()[::-1]:
            text = self.sitesBox.GetString(item)
            siteID = int(text.split(':')[0])
            self.selectedSites.remove(interfaces.stageMover.getSite(siteID))
            interfaces.stageMover.deleteSite(siteID)
            self.sitesBox.Delete(item)
        self.Refresh()


    ## Move the selected sites by an offset.
    def offsetSelectedSites(self, event = None):
        items = self.sitesBox.GetSelections()
        if not items:
            # No selected sites.
            return
        offset = gui.dialogs.offsetSitesDialog.showDialogModal(self)
        if offset is not None:
            for item in items:
                siteID = int(self.sitesBox.GetString(item).split(':')[0])
                site = interfaces.stageMover.getSite(siteID)
                # Account for the fact that the site position may be a
                # (non-mutable) tuple; cast it to a list before modifying it.
                position = list(site.position)
                for axis, value in enumerate(offset):
                    position[axis] += value
                site.position = tuple(position)
            # Redisplay the sites in the sitesbox.
            self.sitesBox.Clear()
            for site in interfaces.stageMover.getAllSites():
                self.onNewSiteCreated(site, shouldRefresh = False)
            self.Refresh()


    ## Save sites to a file.
    def saveSitesToFile(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = "Please select where to save the file.",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            return
        interfaces.stageMover.writeSitesToFile(dialog.GetPath())


    ## Load sites from a file.
    def loadSavedSites(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_OPEN, wildcard = '*.txt',
                message = "Please select the file to load.",
                defaultDir = util.user.getUserSaveDir())
        if dialog.ShowModal() != wx.ID_OK:
            return
        interfaces.stageMover.loadSites(dialog.GetPath())


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
        if self.amGeneratingMosaic:
            self.onAbort()
            self.amGeneratingMosaic = False
            return

        self.showCameraMenu("Make mosaic with %s camera",
                self.generateMosaic)


    ## Display a menu to the user letting them choose which camera
    # to use to continue generating a pre-existing mosaic. Very
    # similar to self.displayMosaicMenu.
    def continueMosaic(self):
        # If we're already running a mosaic, stop it instead.
        if self.amGeneratingMosaic:
            self.onAbort()
            self.amGeneratingMosaic = False
            return

        self.shouldPauseMosaic = False
        self.amGeneratingMosaic = True
        self.nameToButton['Run mosaic'].SetLabel('Stop mosaic')


    ## Generate a menu where the user can select a camera to use to perform
    # some action.
    # \param text String template to use for entries in the menu.
    # \param action Function to call with the selected camera as a parameter.
    def showCameraMenu(self, text, action):
        cameras = []
        for camera in depot.getHandlersOfType(depot.CAMERA):
            if camera.getIsEnabled():
                cameras.append(camera)
        if len(cameras) == 1:
            action(cameras[0])
        else:
            menu = wx.Menu()
            for i, camera in enumerate(cameras):
                menu.Append(i + 1, text % camera.descriptiveName)
                wx.EVT_MENU(self.panel, i + 1,
                        lambda event, camera = camera: action(camera))
            gui.guiUtils.placeMenuAtMouse(self.panel, menu)


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


    ## Save the mosaic to disk. We generate a text file describing the
    # locations of the mosaic tiles, and an MRC file of the tiles themselves.
    def saveMosaic(self, event = None):
        dialog = wx.FileDialog(self, style = wx.FD_SAVE, wildcard = '*.txt',
                message = "Please select where to save the file.",
                defaultDir = util.user.getUserSaveDir())
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
            except Exception, e:
                print "Failed to get tile data at %s: %s" % (tile.pos, e)
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
            for j in xrange(data.shape[0] / 3, 2 * data.shape[0] / 3, regionSize / 4):
                for k in xrange(data.shape[1] / 3, 2 * data.shape[1] / 3, regionSize / 4):
                    region = thresholded[j : j + regionSize, k : k + regionSize]
                    # Skip overly small regions (on the off-chance that 
                    # regionSize is a significant portion of the tile size).
                    if region.shape[0] < regionSize or region.shape[1] < regionSize:
                        continue
                    # Find connected components in data.
                    labeled, numComponents = scipy.ndimage.measurements.label(region)
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
                    maxDistSquared = max(map(sum, zip(xDists, yDists)))
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
                interfaces.stageMover.goTo((x, y, z + offset), shouldBlock = True)
                image, timestamp = events.executeAndWaitFor('new image %s' % camera.name,
                        interfaces.imager.takeImage, shouldBlock = True)
                if bestIntensity is None or image.max() > bestIntensity:
                    bestIntensity = image.max()
                    bestOffset = offset
            newSite = interfaces.stageMover.Site((x, y, z + bestOffset),
                    group = 'beads', size = 2)
            wx.CallAfter(interfaces.stageMover.saveSite, newSite)
        statusDialog.Destroy()
        wx.CallAfter(self.Refresh)


    ## Handle the user clicking the abort button.
    def onAbort(self, *args):
        self.shouldAbort = True
        if self.amGeneratingMosaic:
            self.shouldPauseMosaic = True
        self.nameToButton['Run mosaic'].SetLabel('Run mosaic')
        # Stop deleting tiles, while we're at it.
        self.onDeleteTiles(shouldForceStop = True)



## Global window singleton.
window = None


def makeWindow(parent):
    global window
    window = MosaicWindow(parent, title = "Mosaic view",
            style = wx.CAPTION | wx.MINIMIZE_BOX)
    window.Show()
    window.centerCanvas()


## Transfer a camera image to the mosaic.
def transferCameraImage():
    window.transferCameraImage()

