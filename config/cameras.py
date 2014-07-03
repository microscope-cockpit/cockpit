def enum(*args):
    enums = dict(zip(args, range(len(args))))
    return type('Enum', (), enums)

CAMTYPES = enum('IXON','IXON_PLUS','IXON_ULTRA','ZYLA')

## _cameras [(label, dsp line, ip address, model)]
cameras = [
    ('West', 1<<0, '172.16.0.20', CAMTYPES.IXON),
    ]
camera_keys = ['label', 'line', 'ipAddress', 'model']
