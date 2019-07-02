.. Copyright (C) 2019 David Pinto <david.pinto@bioch.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Installation
************

Cockpit does not yet have a release and is not available on PyPI.  It
can however, be installed from development sources::

    git clone git@github.com:MicronOxford/cockpit.git
    cd cockpit
    python3 setup.py install

Cockpit `setup.py` script will automatically check and install its
Python dependencies.  Its main dependencies are microscope, numpy,
PyOpenGL, Pyro4, and wxPython.

The only non Python dependency is `FTGL
<https://sourceforge.net/projects/ftgl/>`_ which needs to be installed
separately.
