#!/usr/bin/env python
# -*- coding: utf-8 -*-

## _cameras [(label, dsp line, ip address, model)]
# As of 2015/04/23, UCSF's OMXT code only makes use of the 'label', 'serial',
# 'ipAddress', 'port', and 'model' fields.  The digital line is still
# hardwired in dsp.py so the value here is ignored.  At some point in the
# near future, intend on using the value from here.  Do not know how the
# 'dyes' and 'wavelength' fields will be used with UCSF's OMXT.  The camera
# remotes do not yet use this configuration file.
cameras = [
    ('Zyla', 'VSC-00621', 1<<0, '10.0.0.2', 7000, 'zyla', ['GFP', 'mCherry'], [520, 585]),
    ('iXon1', '1970', 1<<1, '192.168.137.101', 7767, 'ixon', ['GFP', 'mCherry'], [520, 585]),
    ]
camera_keys = ['label', 'serial', 'triggerLine', 'ipAddress', 'port', 'model', 'dyes', 'wavelengths']
