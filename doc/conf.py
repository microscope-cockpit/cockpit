#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2019 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## Copying and distribution of this file, with or without modification,
## are permitted in any medium without royalty provided the copyright
## notice and this notice are preserved.  This file is offered as-is,
## without any warranty.

import sys

sys.path.insert(0, '../cockpit')


## This should be read from setup.py.  Maybe we should use
## pkg_resources to avoid duplication?
author = 'Micron Oxford'
project = 'Cockpit'
copyright = '2019, Micron Oxford'


master_doc = 'index'


extensions = [
  'sphinx.ext.autodoc',
  'sphinx.ext.napoleon',
  'sphinx.ext.todo',
  'sphinx.ext.viewcode',
]

## Configuration for sphinx.ext.todo
todo_include_todos = True

## Configuration for sphinx.ext.napoleon
napoleon_google_docstring = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = True


##
## Options for HTML output
##

html_theme = 'agogo'
