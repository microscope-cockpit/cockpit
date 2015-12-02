import depot
import events
import util.threads

import time
import traceback

## This module provides an interface for taking images with the current
# active cameras and light sources. It's used only outside of experiment
# mode.



## Simple container class.
class Imager:
    def __init__(self):
        ## List of Handlers capable of taking images.
        self.imageHandlers = depot.getHandlersOfType(depot.IMAGER)
        ## Set of active cameras, so we can check their framerates.
        self.activeCameras = set()
        events.subscribe('camera enable',
                lambda c, isOn: self.toggle(self.activeCameras, c, isOn))
        ## Set of active light sources, so we can check their exposure times.
        self.activeLights = set()
        events.subscribe('light source enable',
                lambda l, isOn: self.toggle(self.activeLights, l, isOn))
        ## Time of last call to takeImage(), so we can avoid calling it
        # faster than the time it takes to actually collect another image.
        self.lastImageTime = time.time()
        ## Boolean to control activity of the video mode thread.
        self.shouldStopVideoMode = False
        ## Boolean that indicates if we're currently in video mode.
        self.amInVideoMode = False
        events.subscribe('user abort', self.stopVideo)


    ## Add or remove the provided object from the specified set.
    def toggle(self, container, thing, shouldAdd):
        if shouldAdd:
            container.add(thing)
        elif thing in container:
            container.remove(thing)


    ## Take an image.
    # \param shouldBlock True if we want to wait for the cameras and lights
    #        to be ready so we can take the image; False if we don't want to
    #        wait and should just give up if they aren't ready.
    # \param shouldStopVideo True if we should stop video mode. Only really
    #        used by self.videoMode().
    def takeImage(self, shouldBlock = False, shouldStopVideo = True):
        if shouldStopVideo:
            self.stopVideo()
        waitTime = self.getNextImageTime() - time.time()
        if waitTime > 0:
            if shouldBlock:
                time.sleep(waitTime)
            else:
                return
        for handler in self.imageHandlers:
            handler.takeImage()
        self.lastImageTime = time.time()


    ## Video mode: continuously take images at our maximum update rate.
    # We stop whenever the user invokes takeImage() manually or the abort
    # button is pressed. We also limit our image rate if there are any
    # non-room-light light sources to 1 image per second, to avoid excessive
    # sample damage.
    @util.threads.callInNewThread
    def videoMode(self):
        if not self.activeCameras:
            # No cameras, no video mode.
            events.publish('video mode toggle', False)
            return
        if self.amInVideoMode:
            # Just cancel the current video mode.
            events.publish('video mode toggle', False)
            self.shouldStopVideoMode = True
            self.amInVideoMode = False
            return

        events.publish('video mode toggle', True)
        self.shouldStopVideoMode = False
        self.amInVideoMode = True
        while not self.shouldStopVideoMode:
            haveNonRoomLight = False
            for light in self.activeLights:
                if light.name != 'Ambient light':
                    haveNonRoomLight = True
                    break
            start = time.time()
            try:
                # HACK: only wait for one camera.
                events.executeAndWaitFor("new image %s" % (list(self.activeCameras)[0].name),
                        self.takeImage, 
                        shouldBlock = haveNonRoomLight, shouldStopVideo = False)
            except Exception, e:
                print "Video mode failed:",e
                events.publish('video mode toggle', False)
                traceback.print_exc()
                break
#            if haveNonRoomLight:
#                waitTime = 1 - (time.time() - start)
#                # Wait until 1s has passed before taking the next image.
#                time.sleep(max(0, 1 - time.time() + start))
#            else:
#                time.sleep(.01)
        self.amInVideoMode = False
        events.publish('video mode toggle', False)


    ## Stop our video thread, if relevant.
    def stopVideo(self):
        self.shouldStopVideoMode = True


    ## Get the next time it's safe to call takeImage(), based on the
    # cameras' time between images and the light sources' exposure times.
    def getNextImageTime(self):
        camLimiter = 0
        for camera in self.activeCameras:
            camLimiter = max(camLimiter, camera.getTimeBetweenExposures())
        lightLimiter = 0
        for light in self.activeLights:
            lightLimiter = max(lightLimiter, light.getExposureTime())
        # The limiters are in milliseconds; downconvert.
        return self.lastImageTime + (camLimiter + lightLimiter) / 1000.0
        
        


## Global singleton.
imager = None

def initialize():
    global imager
    imager = Imager()


def makeInitialPublications():
    pass


## Simple passthrough.
def takeImage(shouldBlock = False):
    imager.takeImage(shouldBlock)


## Simple passthrough.
def videoMode():
    imager.videoMode()
        
