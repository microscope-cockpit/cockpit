===Introduction===

This file gives an overview of the code in the MUI codebase. More specific
documentation will be in the comments in the individual files themselves, or 
in README.txt files within subdirectories. 

This document was initially written by Chris Weisiger (cweisiger@msg.ucsf.edu).
If I dip into first-person from time to time, that's probably who I'm talking
about.

MUI is a microscope user interface system, designed to maintain good separation
between the GUI and the actual hardware. While you can draw similarities to 
MicroManager, MUI is really about the user interface, while MicroManager is
more about the hardware and supporting large numbers of devices. Getting them
to work together nicely is a long-term goal in MUI development. 

===Device code===

MUI "device code" is the code that actually talks to devices (or talks to 
code that talks to devices, etc.). In other words, it's the code that is 
specific to your particular microscope. I've written three sets of MUI device
code, in three subdirectories:

 * devices: this is a set of simulated devices, enough to show off MUI's 
   interface and test its UI. The camera generates test patterns, and 
   everything else is largely just stub functions.
 * devices-omx: code for talking to the OMX microscope on the 4th floor of 
   Genentech Hall. 
 * devices-omxt: code for talking to the OMXT microscope on the 1st floor of
   Genentech Hall. 

Note that the program automatically loads whatever is in the "devices" 
directory when it starts up. Thus if you don't want to use the simulated 
devices, you need to do some directory renaming (e.g. rename "devices" to 
"devices-sim", and "devices-omx" to "devices"). I admit this is confusing; my
apologies. 

devices-omx and devices-omxt have several similarities; they both have iXon
EMCCD cameras and a DSP card, for example. As a result there's some degree of 
code duplication between them. In an ideal world they'd share that code and 
just have configuration tweaks between them, but instead I've just been 
manually merging them whenever there's been major changes in the underlying
code.

===Handler code===

DeviceHandler instances are the primary way that device code communicates with
the UI (and vice versa). Each DeviceHandler module (in the "handlers" 
directory) represents an abstracted bit of hardware: a camera, a light source, 
a stage positioner, etc. MUI will automatically build its user interface based
on the DeviceHandlers that the device code creates. So if you want to add 
a new camera to the system, then you would create a module in your "devices"
directory, with a Device subclass in it that, in its getHandlers() function,
generates and returns a CameraHandler instance. 

The DeviceHandlers each have different defined functions (e.g. a 
PositionerHandler has moveRelative() and moveAbsolute(). These functions in
turn invoke callback functions specified by your device code, which then 
presumably talks to the hardware. 

In short, MUI talks to the DeviceHandler, the DeviceHandler talks to your 
Device, your Device talks to the hardware. 

===Event handling===

MUI has a simple internal event publishing system, in the events.py module. 
This system allows for an alternate method of communication between the 
UI and device code. Any code may subscribe to an event (which is just a 
string, like "stage position" or "experiment execution"). Likewise any code 
may publish an event, along with associated data. When an event is published, 
all subscribers to the event have their functions called. 

The UI subscribes to some events (wanting to know e.g. when a new camera image
arrives or when the stage changes position). Device code is responsible for
generating these events. Likewise, the UI will publish some events which
device code is responsible for subscribing to, if it wants to respond when 
e.g. an experiment is about to start. README.txt has more information about
what specific events are available.

===UI code===

If you want to follow program flow, you should start in cockpit.pyw and 
depot.py. The former file has the full initialization routine, setting up the 
devices and the interface. The latter is responsible for more device-specific
functions, including automatically finding new device modules and running them
through their initialization routines. Check out devices/device.py for more 
information on what a device module is responsible for doing. 

UI initialization largely involves loading up windows that are defined in the 
"gui" subdirectory. In particulary, gui/mainWindow.py creates the window that
allows the user to set up exposure settings and run experiments. 

Once initialization is completed, we simply enter the event loop (provided by
the wxPython library) and wait for the user to do something. 

=== CUSTOMIZATION ===
Of course, the cockpit isn't much good without any hardware. The "devices" 
directory should be the only directory that you will need to modify; it's here
that you can hook up your hardware to the cockpit. 

Each device module should follow this general pattern:

import device
CLASS_NAME = "MyDevice"

class MyDevice(device.Device):
    ...

All you need to do is create the module; all valid Devices are created when 
the program starts.

The primary task that Devices are responsible for is creation of DeviceHandlers.
Each Handler represents an abstract bit of hardware, for example a camera or
stage mover. The getHandlers() function is expected to generate and return
a list of Handlers; the UI then interacts with these Handlers when the user 
performs actions. Take a look at the "devices/handlers" directory for the 
available handlers. 

=== EVENTS ===
MUI includes an event-publishing system to handle some communications between
different components. An "event" is simply a string and some associated data.
Code can "subscribe" to a specific event; when other code "publishes" that
event, then the subscribers are all called. For example, if you have some 
code that wants to know when the user clicks on the "abort" button, then
you would do this:

import events
events.subscribe('user abort', self.onAbort)

def onAbort(self):
    ...

If your code wants to let the rest of the program know that a new camera 
image has appeared, then you would do this:

import events
events.publish('new image %s' % cameraName, imageData)

A complete list of all events that the system currently supports is below. 
Some of your devices will need to publish these events; some of them are 
generated by the UI instead and your devices will need to subscribe to them.

Device-generated events:
 * "drawer change", drawer settings: the filters in front of each camera are
   different (DEVICE)
 * "experiment execution": some component of the currently-running experiment
   has finished (DEVICE)
 * "new image <camera name>", image data: An image has arrived for the camera
   with the given name (DEVICE)
 * "stage mover", moverName: A StagePositioner Handler is moving (DEVICE)
 * "stage stopped", moverName: A StagePositioner Handler has stopped moving
   (DEVICE)

UI-generated events:
 * "experiment complete": the entirety of an experiment has finished execution
   (UI)
 * "image pixel info", coordinates, value: the mouse has moved over a camera
   view, and the specified coordinates have the given value (UI)
 * "new site", Site instance: the user has marked a position as being of
   interest (UI)
 * "prepare for experiment", Experiment instance: An experiment is about to be
   executed, so devices should prepare themselves (UI)
 * "site deleted", Site instance: the specified Site is to be forgotten (UI)
 * "soft safety limit", axis, limit, isMax: the software-enforced motion
   limits for the given axis (summing all stage-positioner devices) have been
   changed (UI)
 * "stage position", position tuple: the stage currently is at the specified
   position (UI)
 * "stage step index", index: Which Handler is currently being used to move
   the stage has been changed; the Handlers are arranged in order of maximum
   range of motion (UI)
 * "stage step size", axis, step size: The amount of distance the stage will
   move when the user uses the numeric keypad has changed (UI)
 * "user abort": the user clicked on the Abort button (UI)
 * "user login", user name: the specified user has logged in (UI)
 * "user logout": the current user is logging out (UI)

Handler-generated events:
 * "global filter change", filter ID, filter position: A light attenuation
   filter that is on all light sources' paths has changed, so the transmission
   values for each light source must be recalculated (HANDLER)
 * "light source (enable|disable)", handler: the light source associated with
   the provided Handler has been enabled / disabled for taking images (HANDLER)
 * "objective change", objective name, pixel size: the objective has been
   changed (HANDLER)

Miscellaneous events:
 * "new status light", lightName, text, color: Create a new "status light" 
   that shows the user some bit of important hardware state.
 * "update status light", lightName, newText, newColor: Change one of the 
   status lights.
