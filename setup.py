#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## Copying and distribution of this file, with or without modification,
## are permitted in any medium without royalty provided the copyright
## notice and this notice are preserved.  This file is offered as-is,
## without any warranty.

import glob
import os.path

import setuptools
import setuptools.command.sdist


## Modify the sdist command class to include extra files in the source
## distribution.  We could also have a MANIFEST file but we'd rather
## not have the distribution configuration over multiple files.
manifest_files = [
    'README.rst',
    'INSTALL.rst',
    'COPYING',
    os.path.join('cockpit', 'resources', 'fonts', 'Universalis_COPYING.txt'),
    os.path.join('cockpit', 'resources', 'fonts', 'Universalis_NOTICE.txt'),
    os.path.join('aux', 'convert-images-to-png.py'),
] + glob.glob(os.path.join('images', 'touchscreen', '*.svg'))

class sdist(setuptools.command.sdist.sdist):
    def make_distribution(self):
        self.filelist.extend(manifest_files)
        super(sdist, self).make_distribution()


setuptools.setup(
    name = 'microscope-cockpit',
    version = '2.9.1+dev',
    description = 'Hardware agnostic microscope user interface',
    long_description = open('README.rst', 'r').read(),
    license = 'GPL-3.0+',

    url = "https://github.com/MicronOxford/cockpit",

    author = 'See source for a complete list of contributors',
    author_email = ' ',

    ## https://pypi.org/pypi?:action=list_classifiers
    classifiers = [
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    ],

    packages = setuptools.find_packages(),
    package_data = {
        'cockpit' : [
            os.path.join('resources', 'images', 'touchscreen', '*.png'),
            os.path.join('resources', 'images', '*.icns'),
            os.path.join('resources', 'images', '*.ico'),
            os.path.join('resources', 'fonts', '*.otf'),
        ],
    },

    python_requires = '>=3.5',
    install_requires = [
        'PyOpenGL',
        'Pyro4',
        'freetype-py',
        'matplotlib',
        'microscope>=0.5',
        'numpy',
        'pyserial',
        'scipy',
        'wxPython>=4.1',
    ],

    test_suite = 'cockpit.testsuite',

    entry_points = {
        'gui_scripts': [
            'cockpit = cockpit:_setuptools_entry_point',
        ]
    },

    cmdclass = {
        'sdist' : sdist,
    },
)
