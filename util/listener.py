import Pyro4
import depot

## Similar to the util.connection.Connection class.
# Several device classes need to register functions with the cockpit
# server to receive data from the remote object. The Connection class
# implements this, using its own Pyro proxy, but it is implemented so
# that there are two states:
#   connected, with BOTH an active Pyro proxy and a registered function;
#   disconnected, with NEITHER proxy nor function.
# There are some classes that need a Pyro proxy even when they are not
# listening - the proxy may be needed for configuration, or polling
# state. The workaround has been to keep a copy of Connection's proxy
# around, but this is messy.
# Instead, this Listener class takes a Pyro proxy as an argument to 
# __init__, and only deals with registering and unregistering listener
# functions.
class Listener:
    def __init__(self, pyroProxy, callback=None, localIp=None):
        ## Extant connection to the camera.
        self._proxy = pyroProxy
        ## The callback function
        self._callback = callback
        ## Are we listening?
        self._listening = False
        ## Local cockpit server IP address
        self._localIp = localIp


    ## Establish a connection with the remote service, and tell
    # it to send us its data.
    # By default we set a short timeout of 5s so that we find out fairly
    # quickly if something went wrong.
    def connect(self, callback=None, timeout = 5):
        server = depot.getHandlersOfType(depot.SERVER)[0]
        if self._listening:
            server.unregister(self._callback)
        if callback:
            self._callback = callback
        elif not self._callback:
            # No callback specified in either self._callback or this call.
            raise Exception('No callback set.')
        uri = server.register(self._callback, self._localIp)
        self._proxy.receiveClient(uri)
        self._listening = True


    ## Stop listening to the service.
    def disconnect(self):
        if not self._listening:
            # Nothing to do.
            return
        server = depot.getHandlersOfType(depot.SERVER)[0]
        server.unregister(self._callback)
        try:
            self._proxy.receiveClient(None)
        except Exception, e:
            print ("Couldn't disconnect listener from %s: %s" % (self._proxy, e))
        self._listening = False
