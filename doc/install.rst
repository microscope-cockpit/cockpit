.. Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Installation
************

.. include:: ../INSTALL


Linux
=====

Linux systems have their package manager but Cockpit and some of its
dependencies are not always available.  To avoid conflicts, it's a
good idea to avoid installing packages with the Python package manager
if they are available via the system package manager.

Debian based distributions (such as Ubuntu)
-------------------------------------------

The Cockpit dependencies not available on Debian repositories are
`microscope <https://pypi.org/project/microscope/>`_ and `freetype-py
<https://pypi.org/project/freetype-py/>`_ which can be installed with
`pip`.  To avoid having `pip` installing the other dependencies from
PyPI, they need to be installed first with `apt`::

  sudo apt install \
    python3 \
    python3-matplotlib \
    python3-numpy \
    python3-opengl \
    python3-pip \
    python3-pyro4 \
    python3-scipy \
    python3-serial \
    python3-setuptools \
    python3-wxgtk4.0

Once that is done, installing Cockpit with `pip` will also install the
other dependencies::

  pip3 install --user microscope-cockpit


macOS
-----

The easiest method to install cockpit on macOS is to install the
python.org build of the latest python version and then use the pip to
install cockpit and its dependencies.

First download and install the latest python 3 from `python.org
<https://www.python.org/downloads/mac-osx/>`_.

Once python is installed open a terminal window
(``/Application/Utilities/Terminal``) and use pip to install cockpit.
You must use 'pip3' as this will run the newly installed python3
rather than the system default Python 2.7 which cockpit does not
support::

  pip3 install microscope-cockpit

This may prompt you to install the XCode command line utilities.
Please install these as they are required for some of the instrument
control functionality in Cockpit (they are required to build hidapi
used in microscope).  If this step is required you will have to rerun
the pip3 install command above as it will have failed the first time.

Once installed, cockpit can be started from command line::

 cockpit


Microsoft Windows
=================

Python must be installed first, and the installer can be downloaded
from `python.org <https://www.python.org/downloads/windows/>`_.
During the Python installation, ensure that pip is also installed (it
will be by default) and that the install and scripts directories are
added to Windows ``PATH`` (check the "Add Python X.Y to PATH" option
during installation).

Once Python is installed, Cockpit can be installed with pip like so::

  pip install microscope-cockpit


Development sources
===================

Cockpit development happens in a public git repository making it
possible to install cockpit from development sources::

  git clone https://github.com/MicronOxford/cockpit.git
  pip install --no-index cockpit/

If the plan is to make changes to the source code or to have the
installed version follow development, consider installing in develop
mode, also known as editable mode::

  pip install --no-index --editable cockpit/
