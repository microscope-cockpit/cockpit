import os
from ConfigParser import ConfigParser

_path = __path__[0]
_files = [os.path.sep.join([_path, file])
            for file in os.listdir(_path) if file.endswith('.conf')]

try:
    _files.append(_files.pop(_files.index(
        os.path.sep.join([_path,'master.conf']))))
    _files.reverse()
    print _files
except:
    pass

print _files
config = ConfigParser()
print config.read(_files)
