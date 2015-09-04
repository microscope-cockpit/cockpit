cameras = [
    #('Zyla', 'VSC-00621', 1<<0, '10.0.0.2', 7000, 'zyla', ['GFP', 'mCherry'], [520, 585])
    ('West', 9146, 1<<2, '127.0.0.1', 7777, 'ixon', ['GFP', 'mCherry'], [525, 585]),
    ('East', 9145, 1<<1, '127.0.0.1', 7776, 'ixon', ['Cy5', 'FITC'], [670, 518]),
    ]
camera_keys = ['label', 'serial', 'triggerLine', 'ipAddress', 'port', 'model', 'dyes', 'wavelengths']