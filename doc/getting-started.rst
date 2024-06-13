.. Copyright (C) 2021 Martin Hailstone <martin.hailstone@engs.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Getting Started
###############

If Cockpit is being installed for the first time and in the absence of
any configuration files, Cockpit simulates a series of devices.  While
this is useful for testing, the goal of Cockpit is to control a real
microscope.  Configuring Cockpit to connect and control your own
devices requires two things:

1. Setup a Python-Microscope `device-server
   <https://www.python-microscope.org/doc/architecture/device-server.html>`__
   for each of devices to be used.

2. Configure :ref:`Cockpit's depot <depot-config>` to use those
   devices.

Configuration of the device servers is outside the scope of this
documentation, refer to Microscope's `documentation
<https://www.python-microscope.org/doc/architecture/device-server.html>`__.
This document is about configuring Cockpit proper.

Configuring Cockpit for the first time
======================================

If running Cockpit for the first time there will be no configuration
files present.  These can be created with any text editor in a
platform and specific :ref:`location <default-config-locations>`.  The
"best" location is also use case specific.  For example, if this is an
end-user system, i.e., users are not expected to be making changes,
then a system wide configuration is better suited.  In the specific
case of Microsoft Windows, the system-wide file to configure what
devices to use is ``C:\ProgramData\cockpit\depot.conf``.

The format of this file is defined in the :ref:`Depot configuration
<depot-config>` section but it might be simpler to start with someone
else's file as a starting point.  Some example configuration files can
be found `here <https://github.com/MicronOxford/configs>`__.

An alternative approach is to start with no configuration file which
will run cockpit with a predefined set of simulated devices. You can
then start adding devices to the depot config file one at a
time. Restart cockpit to test each device to ensure it is working. As real
devices are added the simulated device will be deactivated. 
testing each as it is 

Once the file is created, verify that the depot file is working
correctly, and devices are connected with::

    python3 -m cockpit.status

Critical Components
===================

Cockpit was developed for performing experiments with highly
dependable timing. For this reason the experiment module is designed
around having an external hardware timing device, referenced in the
code as the ``executor``. This device accepts a table of timings for
the experiment and then is able to generate digital triggers and
optionally analog voltage signals at specified timings. There are two
currently supported options, a Red Pitaya single board computer, or a
National Instruments cRO FPGA card.

Additionally Cockpit requires a motorized stage, at least one camera,
at least one light source and at least one objective.
