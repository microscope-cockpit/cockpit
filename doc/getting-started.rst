.. Copyright (C) 2021 Martin Hailstone <martin.hailstone@engs.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Getting Started
###############

Cockpit will run by default with a set of dummy devices.  Configuring
Cockpit to use your own devices requires two things:

- First, you need to setup a Python-Microscope `device-server
  <https://www.python-microscope.org/doc/architecture/device-server.html>`_
  for each of devices to be used.

- Next, you need to configure :ref:`Cockpit's depot <depot-config>` to
  use those devices.
