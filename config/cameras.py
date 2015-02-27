## _cameras [(label, dsp line, ip address, model,dyes,wavelengths,transforms,)]
cameras = [
    ('West', 9146, 1<<8, '192.168.1.2', 7777, 'ixon', ['GFP', 'mCherry'], [525, 585], (0,0,1)),
    ('East', 9145, 1<<9, '192.168.1.2', 7778, 'ixon', ['Cy5', 'FITC'], [670, 518], (0,0,1)),
    ]
camera_keys = ['label', 'serial', 'line', 'ipAddress', 'port', 'model', 'dyes', 'wavelengths','baseTransform']
#transform order [0]=rot90,[1]=flip_h,[2]=flip_v