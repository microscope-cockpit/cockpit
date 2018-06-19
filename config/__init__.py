#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Configuration package for cockpit.

Copyright 2014-2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
=============================================================================

Looks for .conf files in the package directory, loads them into a
ConfigParser, then exposes that parser as cockpitconfig.config.

Default configuration can be specified in default.conf.  This is
processed first, so will be over-ridden if a section with the same
name appears in another file.
"""
import os
import time
import shutil
from six.moves.configparser import ConfigParser

class MyConfigParser(ConfigParser, object):
    def __init__(self):
        super(MyConfigParser, self).__init__()
        self.fileToSections = {}
        self.sectionToFile = {}


    def read(self):
        """Read in the config, tracking which file specifies each section.

        This will update any settings and add any new sections found.
        Note that:
        * this function does not search for new files;
        * sections/keys removed from files will not be removed from loaded config.
        """
        for f in _files:
            lastSections = set(self.sections())
            super(MyConfigParser, self).read(f)
            self.fileToSections[f] = set(self.sections()).difference(lastSections)
            for s in self.fileToSections[f]:
                self.sectionToFile[s] = f


    def writeSection(self, section):
        """Update the section specified in its config file."""
        # Which file provided this section?
        filename = self.sectionToFile.get(section)
        if not filename:
            raise Exception("This section did not come from a file.")
        # Back up the old config file.
        timestamp = time.strftime('%Y%m%d-%H%M%S', time.localtime())
        shutil.copyfile(filename, '.'.join( (filename, timestamp, 'bak') ))
        # Temporarily remove sections sourced from other files.
        for s in self._sections:
            if not s in self.fileToSections[filename]:
                self.remove_section(s)
        # Should now be left only with sections from our file. Write them out.
        with open(filename, 'w') as file:
            self.write(file)
        # Re-read to recover discarded sections.
        self.read()


_path = __path__[0]
_files = [os.path.sep.join([_path, file])
            for file in os.listdir(_path) if file.endswith('.conf')]

try:
    _files.append(_files.pop(_files.index(
        os.path.sep.join([_path,'default.conf']))))
    _files.reverse()
except:
    pass

config = MyConfigParser()
config.read()
