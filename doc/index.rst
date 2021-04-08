.. Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Microscope-Cockpit
##################

.. toctree::
   :maxdepth: 2
   :hidden:

   install
   getting-started
   config
   architecture
   troubleshoot

Cockpit is a microscope graphical user interface.  It is a flexible
and easy to extend platform aimed at life scientists using bespoke
microscopes. Its main features are:

- Easy to use and extend by life scientists.  Cockpit is completely
  written in Python and meant to be extended by the user.

- Independent of the actual devices being used.  Cockpit uses Python's
  `microscope <https://www.python-microscope.org>`__ package to
  control the devices.  The graphical interface and experiments
  automatically adjust to the existing devices.

- Very fast device control and time precision.  During experiments,
  devices are controlled via hardware signals.

- Cross Platform.  Cockpit can run on GNU/Linux, macOS, and Windows.

- Cockpit is free and open source software, released under the GPL.

A more detailed description is available in the `associated
publication <https://doi.org/10.12688/wellcomeopenres.16610.1>`__.

The User Interface
==================

The user interface is made up of a number of windows with the main
ones shown below.

.. image:: cockpit-windows.png
  :align: center
  :alt: Cockpit main windows
