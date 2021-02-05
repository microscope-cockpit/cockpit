#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## Copying and distribution of this file, with or without modification,
## are permitted in any medium without royalty provided the copyright
## notice and this notice are preserved.  This file is offered as-is,
## without any warranty.

"""Aux script to convert the svg images to png.

Original images used by Cockpit should be in the svg format so they
can be converted to whatever size is needed.  wx will not take svg
images so they must be converted to png ahead of time.

The original svg files and the converted png files are located in the
``images/`` and ``cockpit/resources/images`` respectively.  The svg
files are outside the cockpit package and while they are part of the
source distribution they are not part of the installation.

The png converted files are commited to the source repo but this is
just for convenience and because they are very small.

"""

from pathlib import Path
import subprocess


# TODO: this works because we only have images for the touchscreen.
# Once we have more, we should have this walk the images directory
# tree to convert all svgs.
IN_DIR = Path("images", "touchscreen")
OUT_DIR = Path("cockpit", "resources", IN_DIR)


for in_path in IN_DIR.iterdir():
    if not in_path.is_file():
        continue
    out_path = Path(OUT_DIR, in_path.stem + ".png")
    subprocess.run(
        [
            "inkscape",
            "--file",
            str(in_path),
            "--export-dpi",
            "96",
            "--export-png",
            str(out_path),
        ],
        check=True,
    )
