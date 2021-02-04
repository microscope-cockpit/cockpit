#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## Copying and distribution of this file, with or without modification,
## are permitted in any medium without royalty provided the copyright
## notice and this notice are preserved.  This file is offered as-is,
## without any warranty.

project = "Microscope-Cockpit"
author = ""
copyright = "CC BY-SA"
version = "2.9.1+dev"
release = version


extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
]

master_doc = "index"

nitpicky = True


# Configuration for sphinx.ext.todo
todo_include_todos = True

# Configuration for sphinx.ext.napoleon
napoleon_google_docstring = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = True


#
# Options for HTML output
#

html_theme = "alabaster"
html_theme_options = {
    "description": (
        "A flexible and easy to extend microscope user interface aimed at"
        " life scientists using bespoke microscopes."
    ),
    "github_button": True,
    "github_repo": "cockpit",
    "github_user": "MicronOxford",
    "show_related": False,
    "sidebar_collapse": False,
    "show_powered_by": False,
    "show_relbars": True,
}

html_short_title = "Cockpit documentation"
html_logo = "../cockpit/resources/images/cockpit.ico"
html_favicon = html_logo

html_copy_source = False
html_show_source_link = False

html_show_copyright = False
html_show_sphinx = False
