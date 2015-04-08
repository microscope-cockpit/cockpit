import collections
import Pyro4
import threading
import traceback

import depot
import device
import handlers.server
import util.logger
import util.threads

from config import config

CLASS_NAME = 'CockpitServer'



## This Device represents the cockpit itself, and is mostly used to
# allow other computers to send information to the cockpit program.
# It handles selecting the ports that are used by these other devices,
# so that each incoming connection is on its own port.
class CockpitServer(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        ## We need to be initialized before any devices that want to use the
        # util.connection module, which requires us to exist. Note default
        # priority is 100.
        self.priority = 10
        ## IP address of the cockpit computer.
        if config.has_option('server', 'ipAddress'):
            self.ipAddress = config.get('server', 'ipAddress')
        else:
            self.ipAddress = '127.0.0.1'
        ## Name used to represent us to the outside world.
        self.name = 'mui'
        ## Auto-incrementing port ID.
        self.uniquePortID = 7700
        ## Maps registered functions to the ServerDaemon instances
        # used to serve them.
        self.funcToDaemon = {}


    def getHandlers(self):
        return [handlers.server.ServerHandler("Cockpit server", "server",
                {'register': self.register,
                 'unregister': self.unregister})]
                

    ## Register a new function. Create a daemon to listen to calls
    # on the appropriate port; those calls will be forwarded to
    # the registered function. Return a URI used to connect to that
    # daemon from outside.
    def register(self, func, localIp = None):
        self.uniquePortID += 1
        ipAddress = self.ipAddress
        if localIp is not None:
            # Use the alternate address instead.
            ipAddress = localIp
        daemon = ServerDaemon(self.name, func, self.uniquePortID, ipAddress)
        self.funcToDaemon[func] = daemon
        daemon.serve()
        return 'PYRO:%s@%s:%d' % (self.name, ipAddress, self.uniquePortID)


    ## Stop a daemon.
    def unregister(self, func):
        if func in self.funcToDaemon:
            self.funcToDaemon[func].stop()
            del self.funcToDaemon[func]



class ServerDaemon:
    def __init__(self, name, func, port, host):
        self.name = name
        self.func = func
        self.daemon = Pyro4.Daemon(port = port, host = host)
        self.daemon.register(self, name)


    ## Handle function calls by forwarding them to self.func.
    @util.threads.callInNewThread
    def serve(self):
        self.daemon.requestLoop()


    ## Stop the daemon.
    def stop(self):
        # Per the documentation, these functions must be called
        # in separate threads, or else the process will hang.
        threading.Thread(target = self.daemon.close).start()
        threading.Thread(target = self.daemon.shutdown).start()


    ## Receive a function call from outside.
    # Note that if our caller throws an exception, then we do not propagate
    # it to the client; the assumption is that it's our fault and there's
    # nothing the client can do about the failure.
    def receiveData(self, *args):
        try:
            self.func(*args)
        except Exception, e:
            util.logger.log.error("ServerDaemon [%s] failed its callback: %s" % (self.name, e))
            util.logger.log.error(traceback.format_exc())
