## _cameras [(label, dsp line, ip address, model)]
cameras = [
    ('West', 1<<0, '127.0.0.1', 7777, 'ixon', ['GFP', 'mCherry'], [525, 585]),
    ('East', 1<<1, '127.0.0.1', 7776, 'ixon', ['Cy5', 'FITC'], [670, 518]),
    ]
camera_keys = ['label', 'line', 'ipAddress', 'port', 'model', 'dyes', 'wavelengths']
