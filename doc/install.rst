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

The only Cockpit dependency not available on Debian repositories is
`microscope <https://github.com/MicronOxford/microscope>`_ which can
be installed with `pip`.  To avoid having `pip` installing the other
dependencies from PyPI, they need to be installed first with `apt`::

  sudo apt install \
    git \
    libftgl-dev \
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

Of Microscope's own dependencies, `hidapi
<https://pypi.org/project/hidapi/>`_ is also not available on Debian
repositories.  It will be installed at the same time as microscope
with `pip`::

  pip3 install --user microscope

Finally clone the Cockpit repository and install it::

  git clone cockpit
  pip3 install --user --no-index cockpit/
  rm -r cockpit

	     
Developer install instructions
==============================


macOS
=====

macOS needs git and python3 which are not part of the default
setup. There are various route to get these two packages but below are
instructions for how to do this via homebrew.

Install Homebrew from https://brew.sh/ currently this involves starting
a terminal (/Applications/Utilities/terminal.app) and running the command::

 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"

Then use homebrew to install git and python3 and ftgl::

 brew install git

 brew install python3

 brew install ftgl

Create a directory for microscope and cockpit, I used ~/src::

 mkdir ~/src
 cd ~/src

Next clone the github respoitories::

 git clone https://github.com/MicronOxford/microscope.git
 git clone https://github.com/MicronOxford/cockpit.git

Setup these packages as a developer::

 cd microscope
 python3 setup.py develop

For me this failed as I didn't have write access to the python library
directory /Library/Python/3.7/site-packages. If this is not a problem
move on the the cockpit septup. I had to create this directory and
change its ownership to my userid. As this is a laptop and I am the
only user this shouldn't be a problem::

 sudo mkdir /Library/Python/3.7
 sudo chown <username> /Library/Python/3.7
 mkdir /Library/Python/3.7/site-packages

Then run the setup again::

 python3 setup.py develop

Finally install cockpit in the same way::

 cd ../cockpit
 python3 setup.py develop

Then test::

 cockpit

This should start the cockpit GUI.
