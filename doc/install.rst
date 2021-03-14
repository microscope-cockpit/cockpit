.. Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
   Copyright (C) 2021 Martin Hailstone <martin.hailstone@engs.ox.ac.uk>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Installation
############

Cockpit is available on the Python Package Index (PyPI) and can be
`installed like any other Python package
<https://packaging.python.org/tutorials/installing-packages/>`__.  The
short version is::

    pip install microscope-cockpit

For platform-specific instructions, details, and caveats, see below.

Once installed, Cockpit can be started from command line::

    cockpit

.. note::

    In the absence of configuration files, Cockpit will simulate the
    required devices.  See the :ref:`configuration <configuration>`
    section for details on how to configure Cockpit to control real
    devices.


GNU/Linux
=========

Linux systems have a package manager but Cockpit and some of its
dependencies are not always available.  To avoid conflicts, it is a
good idea to avoid installing packages with the Python package manager
if they are available via the system package manager.

Debian based distributions (such as Ubuntu)
-------------------------------------------

The only Cockpit dependency not available on Debian repositories is
`microscope <https://pypi.org/project/microscope/>`__ which can be
installed with `pip`.  To avoid having `pip` installing the other
dependencies from PyPI, they need to be installed first with `apt`::

    sudo apt install \
      python3 \
      python3-freetype \
      python3-matplotlib \
      python3-numpy \
      python3-opengl \
      python3-pip \
      python3-pyro4 \
      python3-scipy \
      python3-serial \
      python3-setuptools \
      python3-wxgtk4.0

.. note::

   Older versions of Debian and Ubuntu may not have some of the
   dependencies packaged, namely `freetype-py
   <https://pypi.org/project/freetype-py/>`__.  In such case, simply
   omit them from the ``apt install`` command and let `pip` install
   them as part of `pip` automatic handling of missing dependencies.

Once that is done, installing Cockpit with `pip` will install any
missing dependencies::

    pip3 install --user microscope-cockpit


macOS
=====

The easiest method to install Cockpit on macOS is to install the
python.org build of the latest python version and then use `pip` to
install cockpit and its dependencies:

1. Download and install the latest Python 3 from `python.org
<https://www.python.org/downloads/mac-osx/>`__.

2. Once python is installed open a terminal window
(``/Application/Utilities/Terminal``) and use `pip` to install
Cockpit.  You must use ``pip3`` to use the newly installed Python 3
rather than the system default Python 2.7::

    pip3 install microscope-cockpit

3. This may prompt you to install the XCode command line utilities.
Please install these as they are required for some of the instrument
control functionality in Cockpit.  If this step is required you will
have to rerun the ``pip3 install`` command above as it will have
failed the first time.

4. Once installed, cockpit can be started from command line::

    cockpit


Microsoft Windows
=================

Python must be installed first, and the installer can be downloaded
from `python.org <https://www.python.org/downloads/windows/>`__.
During the Python installation, ensure that `pip` is also installed
(it will be by default) and that the install and scripts directories
are added to Windows ``PATH`` (check the "Add Python X.Y to PATH"
option during installation).

Once Python is installed, Cockpit can be installed with pip like so::

    pip install microscope-cockpit


Development sources
===================

Cockpit development happens in a public git repository making it
possible to install cockpit from development sources::

    git clone https://github.com/MicronOxford/cockpit.git
    pip install cockpit/

If the plan is to make changes to the source code or to have the
installed version follow development, consider installing in develop
mode, also known as editable mode::

    pip install --user --editable cockpit/
