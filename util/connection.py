import Pyro4
import depot

## Simple class for managing connections to remote services.
class Connection:
    def __init__(self, serviceName, ipAddress, port, localIp = None):
        ## Name of the service on the remote server.
        self.serviceName = serviceName
        ## IP address to connect to.
        self.ipAddress = ipAddress
        ## Port to connect to.
        self.port = port
        ## Local IP address to use for communication, in the event that this
        # computer has multiple networks to choose from.
        self.localIp = localIp
        ## Function to call when we get something from the camera.
        self.callback = None
        ## Extant connection to the camera.
        self.connection = None


    ## Establish a connection with the remote service, and tell
    # it to send us its data.
    # By default we set a short timeout of 5s so that we find out fairly
    # quickly if something went wrong.
    def connect(self, callback, timeout = 15):
        self.callback = callback
        connection = Pyro4.Proxy(
                'PYRO:%s@%s:%d' % (self.serviceName, self.ipAddress, self.port))
        connection._pyroTimeout = timeout
        self.connection = connection
        server = depot.getHandlersOfType(depot.SERVER)[0]
        uri = server.register(self.callback, self.localIp)
        print(uri)
        print(Pyro4.config.SERIALIZER)
        self.connection.receiveClient(uri)


    ## Remove the connection and stop listening to the service.
    def disconnect(self):
        if self.connection is not None:
            server = depot.getHandlersOfType(depot.SERVER)[0]
            server.unregister(self.callback)
            try:
                self.connection.receiveClient(None)
            except Exception, e:
                print "Couldn't disconnect from %s: %s" % (self.serviceName, e)
            self.connection = None


    ## Return whether or not our connection is active.
    def getIsConnected(self):
        return self.connection is not None
