""" A simple device status script for cockpit.

This script examines cockpit config. files, then reports
the host and port status for each remote device.

Copyright 2015 Mick Phillips (mick.phillips at gmail dot com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import os
import platform
import socket
# Import device definitions from the config module.
from config import config, LIGHTS, CAMERAS

# Strings used for IP address and port in config. files.
IPSTR = 'ipAddress'
PORTSTR = 'port'
# String used to format output.
FORMATSTR = '{:<20}  {:>16}  {:<8}  {:<6}'
# A list of special device types.
IGNORELIST = ['lights', 'cameras', 'server']


def ping(host):
    """
    Returns True if host responds to a ping request.
    """
    ping_str = "-n 1" if  platform.system().lower()=="windows" else "-c 1"
    return os.system("ping " + ping_str + " " + host) == 0


def testPort(host, port):
    """
    Returns True if a port is open.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect( (host, int(port)) )
    except socket.error:
        result = False
    else:
        result = True
    finally:
        s.close()
    return result

# Mappings of device to hosts and ports.
deviceToHost = {}
deviceToPort = {}
# Mappings of device to host and port statuses.
hostsUp = {}
devicesUp = {}

# Iterate over config sections.
for s in config.sections():
    # Skip special devices.
    if s.lower() in IGNORELIST: continue
    # Skip devices that don't have remotes.
    if not config.has_option(s, IPSTR): continue
    # Extract remote details from config and store in dicts.
    host = config.get(s, IPSTR)
    deviceToHost[s] = host
    port = config.get(s, PORTSTR)
    deviceToPort[s] = port

# Lights are special: there is a common ipAddress, but each light
# may have a different port.
host = config.get('lights', IPSTR)
for name, light in LIGHTS.iteritems():
    port = light.get(PORTSTR, None)
    if port:
        deviceToHost['light ' + name] = host
        deviceToPort['light ' + name] = port

# Cameras are special: each one may be on a separate host and port.
for name, camera in CAMERAS.iteritems():
    host = camera.get(IPSTR, None)
    port = camera.get(PORTSTR, None)
    if host and port:
        deviceToHost['cam ' + name] = host
        deviceToPort['cam ' + name] = port

# Iterate over the mappings to query host and port status.
for device, host in deviceToHost.iteritems():
    port = deviceToPort[device]
    if host not in hostsUp.keys():
        hostsUp[host] = 'up' if ping(host) else 'down'
    devicesUp[device] = 'open' if testPort(host, port) else 'closed'

# Report.
print '\n\n'
print FORMATSTR.format('DEVICE', 'HOSTNAME', 'STATUS', 'PORT')
print FORMATSTR.format('======', '========', '======', '====')
for device in sorted(deviceToHost.keys()):
    host = deviceToHost[device]
    port = deviceToPort[device]
    print FORMATSTR.format(device, host, hostsUp[host], devicesUp[device])
