.. Copyright (C) 2021 Ian Dobbie <ian.dobbiue@bioch.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Troubleshooting
***************

This is a brief introduction to troubleshooting the configuration and
running a microscope via Cockpit.  More detailed support can be gained
by raising an issue on the Cockpit `github issues page
<https://github.com/MicronOxford/cockpit/issues>`__.

Startup issues
==============

In general there are two types of startup issues, either the system
does not start at all, or it begins its startup process and displays a
progress window and then fails connecting to a specific device defined
in the configuration files.

No response on startup
----------------------

If you start Cockpit by double clicking on an icon and you receive no
response after this there are few possible causes.  The system may not
be finding a critical component of Cockpit itself, or it may be
crashing while trying to parse its configuration files as these are
read before the window environment is created, and so not displayed.

The best solution to these types of problems is to start Cockpit from
a command prompt instead of clicking on an icon.  If the software is
correctly installed you should be able to open a command prompt and
type:

.. code-block:: bash

    cockpit

By starting from the command line you should get diagnostic output
from Python if errors occur during startup.

If the program halts later in startup there will be windows on the
screen.  The "Initialising Cockpit" window contains a progress bar
indicating how far the process has progressed but it also says which
device is currently being initialised which is almost certainly the
cause of the error.

The "Initialising Cockpit" window might be hidden by the Python errors
window titled "Failed to initialise cockpit".  This can simply be
moved out of the way.  This window will contain a stack of the Python
code which may be beneficial in tracing obscure errors.

An additional status tool is part of cockpit.  This can be run like
so:

.. code-block:: bash

    python -m cockpit.status

This tool takes processes the Cockpit configuration files and then
attempts to connect to all specified devices.  The host machine is
pinged to see if it is on and contactable.  Then a test connection to
the Pyro server of the specified device is performed.  Example output
from this script is below:

.. code-block:: text

    PING 127.0.0.1 (127.0.0.1): 56 data bytes
    64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.053 ms

    --- 127.0.0.1 ping statistics ---
    1 packets transmitted, 1 packets received, 0.0% packet loss
    round-trip min/avg/max/stddev = 0.053/0.053/0.053/0.000 ms

    DEVICE                        HOSTNAME  STATUS    PORT
    ======                        ========  ======    ======
    Testlaser                    localhost  up        open
    cameraB                      localhost  up        open
    cameraG                      localhost  up        open
    cameraR                      localhost  up        closed
    dsp                          127.0.0.1  up        open
    filterwheelB                 localhost  up        open
    filterwheelG                 localhost  up        open
    filterwheelR                 localhost  up        open
    server                       127.0.0.1  up        closed
    stage                        localhost  up        open

    skipped server:  in ignore list
    skipped 40x:  no host or uri
    skipped zPiezo:  no host or uri

In this example it can clearly be seen that ``cameraR`` is closed so
is the device preventing cockpit from starting up.  This error was
produced be deliberately connecting to the wrong port to generate an
error on startup.


Device issues
=============

If Cockpit started successfully then the devices defined in the depot
configuration file must have been alive and able to be connected.
However, most devices do not initialise the hardware until there is an
enable call, generally caused by the user clicking on the control
button for that device in the main window.

Most devices will be able to auto reconnect if something causes the
device server process to stop.  This means that generally devices can
easily be reactivated by restarting the remote device server process,
possibly stopping it first, and then trying to disable and re-enable
the device in the Cockpit interface.  The disable call will fail,
generally giving a red icon next to the device name in the main
window.  If you then click again, Cockpit will try to reconnect to the
device server and re-enable the device.

If restarting the device server and re-enabling the device in Cockpit
does not work, the next step is to try and power cycle the hardware.
First, stop the controlling device server and then either turn off, or
disconnect the power supply.  For directly powered devices such as USB
cameras etc, just unplug the cable.  Leave for a few seconds and
reconnect power, restart the device server and attempt to reconnect
from Cockpit.

If all else fails you might have the close down and restart Cockpit.
This can be done either without restarting the microscope processes,
or by restarting the microscope processes, effectively resetting
everything.

Access to hardware triggers can be gained by opening the "debug
executor" (the exact name of the menu item will be dependent on the
executor name) from the Windows menu.  This debug window provides
toggle buttons for all digital lines as well as text boxes to control
analogue outputs provided by an executor device.

Additional information about specific devices can be gained by
connecting to the device from Cockpit's own Python shell.  From the
Windows menu select "PyShell".  In this shell you can connect to
specific devices with the code:

.. code-block:: python

    from cockpit import depot
    device = depot.getDeviceWithName("NAME")

Where `"NAME"` is the device name from the Cockpit depot file.  The
device object then will allow access to the devices methods and
values.  Exactly what this can tell you is quite device dependant.
This approach gives low level access to all of the devices settings
and methods.


Experiment issues
=================

Experiments are one of the most complex parts of Cockpit and issues
related to running experiments can be difficult to solve.

Fundamentally, experiments involve the creation of an action table
that describes what actions to take at what time.  This action table
is then off loaded to associated hardware, such as a DSP or the Red
Pitaya single board computer, to run the actual experiment.

Experiment issues can often be diagnosed with the help of an
oscilloscope, which can be used to monitor specific signals such as
light or camera triggers, or analogue voltages to control Z piezo
stages.  Studying the existence or absence of the correct trigger
pulses and their relative timing can be very helpful in diagnosing
issues such as mis-synchronisation of lights and cameras.

A useful tool Cockpit provides is a graphical display of what it
thinks the relevant timing signals should look like.  Once an
experiment has been run, the output digital and analogue signals can
be displayed from the "Display last experiment" button in the "debug
executor" window.

Finally it might be useful to examine the remote timing device to see
what it thinks it should have performed.  The Red Pitaya timing device
for example, keeps a copy of all action tables uploaded.
