import os
import platform
import socket
from collections import namedtuple
from config import config, LIGHTS, CAMERAS

IPSTR = 'ipAddress'
PORTSTR = 'port'
#FORMATSTR = '%22s  %18s  %8s  %s'
FORMATSTR = '{:<20}  {:>16}  {:<8}  {:<6}'

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


devicesUp = {}
deviceToHost = {}
deviceToPort = {}
hostsUp = {}

for s in config.sections():
    if s.lower() in ['lights', 'cameras', 'server']: continue
    if not config.has_option(s, IPSTR): continue

    host = config.get(s, IPSTR)
    deviceToHost[s] = host
    port = config.get(s, PORTSTR)
    deviceToPort[s] = port

host = config.get('lights', IPSTR)
for name, light in LIGHTS.iteritems():
    port = light.get(PORTSTR, None)
    if port:
        deviceToHost['light ' + name] = host
        deviceToPort['light ' + name] = port

for name, camera in CAMERAS.iteritems():
    host = camera.get(IPSTR, None)
    port = camera.get(PORTSTR, None)
    if host and port:
        deviceToHost['cam ' + name] = host
        deviceToPort['cam ' + name] = port


for device, host in deviceToHost.iteritems():
    port = deviceToPort[device]
    if host not in hostsUp.keys():
        hostsUp[host] = 'up' if ping(host) else 'down'
    devicesUp[device] = 'open' if testPort(host, port) else 'closed'

print '\n\n'
#print FORMATSTR % ('DEVICE', 'HOSTNAME', 'STATUS', 'PORT')
#print FORMATSTR % ('======', '========', '======', '====')
print FORMATSTR.format('DEVICE', 'HOSTNAME', 'STATUS', 'PORT')
print FORMATSTR.format('======', '========', '======', '====')
for device in sorted(deviceToHost.keys()):
    host = deviceToHost[device]
    port = deviceToPort[device]
    #print FORMATSTR % (device, host, hostsUp[host], devicesUp[device])
    print FORMATSTR.format(device, host, hostsUp[host], devicesUp[device])
