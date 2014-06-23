""" Configuration package for cockpit.

Looks for .conf files in the package directory, loads them into a
ConfigParser, then exposes that parser as cockpitconfig.config.

Default configuration can be specified in default.conf.  This is
processed first, so will be over-ridden if a section with the same
name appears in another file.
"""
import os
from ConfigParser import ConfigParser

_path = __path__[0]
_files = [os.path.sep.join([_path, file])
            for file in os.listdir(_path) if file.endswith('.conf')]

try:
    _files.append(_files.pop(_files.index(
        os.path.sep.join([_path,'default.conf']))))
    _files.reverse()
except:
    pass

config = ConfigParser()
config.read(_files)

