## _cameras [(label, dsp line, ip address, model)]
cameras = [
    ('West', 7197, 1<<0, '172.16.0.20', 7777, 'ixon', ['GFP', 'mCherry'], [525, 585],[0,0,1]),
    ]
camera_keys = ['label', 'serial', 'line', 'ipAddress', 'port', 'model', 'dyes', 'wavelengths','transform']

#transform order [0]= rot90, [1]=flip_h, [2]=flip_v