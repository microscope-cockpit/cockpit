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
