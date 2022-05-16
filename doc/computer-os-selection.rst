.. Copyright (C) 2022 Ian Dobbie <ian.dobbie@jhu.edu>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

.. _Computer_and_OS:

Selection of computer Hardware
******************************

Cockpit is a portable python application that runs on Windows, Linux
and macOS. This allows a very wide range of computers to be used to
run the main GUI application. That said there are a few considerations
to make before selecting the main computer to run the GUI front end
for a microscope.

The strongest determinant of hardware and OS selection is often the
availability of interfaces for the required devices to connect to the
microscope. Many camera have dedicated data transfer cards that
require both a PCIe slot in the computer and a software driver to
interface to the host OS. In many cases this forces the selection of
windows as this is the most widely support OS.

It should be noted that the main controlling computer does not need to
be directly connected to the hardware, devices can easily be on a
remote computer communicating over the network. The main computer and
remote one do not need to run the same OS, eg the controlling computer
can be macOS while the computer hosting the hardware can run
windows. However, many people want some, or all of the devices
connected to the main computer.

CPU requirements
````````````````

In general cockpit is not very demanding of CPU, the heavy graphics
tasks are performed on the system GPU. Cockpit is
multi-threaded but runs in a single Python process so is limited by
the Python global interlock, the so called GIL. This means multi-core
CPUs are unlikely to be fully utilised. However, if you plan to
use the same computer to run devices these will run under a separate
python process and so will be able to exploit more of the power of a
multi-core CPU. 

Memory requirements
```````````````````

Cockpit does not use a huge amount of memory, although additional
memory may considerably help performance with image stacks. The
system stores mosaic images both directly on the GPU for performance
and in memory to allow rescaling so large mosaic considerably add to
the memory footprint. I would recommend at least 16GB.

Graphics Cards
``````````````

The system stores mosaics and live or snapped images on the graphics
card to allow rapid navigation. This can require substantial ram on
the GPU card, especially for large mosaics with 1000's of
images. Any modern graphics card will be able to provide real time
scaling and rendering of these simple images, limited only by the
available graphics memory to store the images.  

Disk Space
``````````

The amount and rate at which image data can be collected in
fundamentally limited by the disk storage space. For rapid image
collection SSD's are much faster, and this performance can be further
increased by using raid to spread the data across multiple
disks. Typically a modern CMOS camera takes images of at least 8MB per
image, multiple z-planes, colour channels and time points can make
extremely large image stacks so ensure you have enough local storage
for fast acquisition and then a network data store, with a data backup
solution, for longer term storage.

Multi-computer configuration
````````````````````````````

In general for high performance systems we run the cockpit GUI from
one computer and connect the actual hardware to other computers to
maximise performance. We connect the computers together with a
dedicated internal network which just contains the computers running
the microscope and then the main computer has 2 networks connected
one for general usage and the other just connecting to the other
microscope computers.

To further improve performance while minimising costs we often drive
multiple cameras from one computer but provide separate network paths
to the front end computer running Cockpit. Both the camera computer and
the cockpit computer require multiple network cards but if each card
is given a separate IP address and each camera is exported via that
address then the large volume of network traffic from the cameras can
easily be separated. 
