""" Configuration package for cockpit.

Looks for .conf files in the package directory, loads them into a
ConfigParser, then exposes that parser as cockpitconfig.config.

Default configuration can be specified in default.conf.  This is
processed first, so will be over-ridden if a section with the same
name appears in another file.
"""
import os
from ConfigParser import ConfigParser

class MyConfigParser(ConfigParser):
	def get(self, section, option, default=None):
		if self.has_option(section, option) or default is None:
			return  ConfigParser.get(self, section, option)
		else:
			return default


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
config.read(_files)

try:
	from lights import light_keys as _light_keys
	from lights import lights as _lights
	from lights import ipAddress as _lightsIpAddress
except:
	LIGHTS = {}
else:
	LIGHTS = {light[0]: dict(zip(_light_keys, light)) for light in _lights}
	config.add_section('lights')
	config.set('lights', 'ipAddress', _lightsIpAddress)

try:
	from cameras import camera_keys as _camera_keys
	from cameras import cameras as _cameras
except:
	CAMERAS = {}
else:
	CAMERAS = {camera[0]: dict(zip(_camera_keys, camera)) for camera in _cameras}

try:
	from analog import aout_keys as _aout_keys
	from analog import aouts as _aouts
except:
	AOUTS = {}
else:
	AOUTS = {aout[0]: dict(zip(_aout_keys, aout)) for aout in _aouts}
