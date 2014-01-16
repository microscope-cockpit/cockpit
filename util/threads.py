import threading
import wx

## Call the passed-in function in a new thread. Used as a decorator when
# a function needs to not block the UI thread.
def callInNewThread(function):
    def wrappedFunc(*args, **kwargs):
        thread = threading.Thread(target = function, args = args, kwargs = kwargs)
        # Ensure the thread will exit when the program does.
        thread.daemon = True
        thread.start()
    return wrappedFunc


## Call the passed-in function in the main thread once the current queue of
# events is cleared. This is necessary for anything that touches the user
# interface or uses OpenGL.
def callInMainThread(function):
    def wrappedFunc(*args, **kwargs):
        wx.CallAfter(function, *args, **kwargs)
    return wrappedFunc


## Maps objects (presumably class instances) to the Locks we maintain
# for those objects.
objectToLock = {}
## Lock around modifying the above.
locksLock = threading.Lock()

## Ensure that the given function cannot be called at the same time as
# other functions wit the same first argument. We assume that the first
# argument is a class instance -- thus, this function effectively forces
# certain member functions in a class to be threadsafe.
def locked(func):
    def wrappedFunc(first, *args, **kwargs):
        with locksLock:
            if first not in objectToLock:
                objectToLock[first] = threading.Lock()
        with objectToLock[first]:
            return func(first, *args, **kwargs)
    return wrappedFunc


