#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


import threading
import wx

## Call the passed-in function in a new thread. Used as a decorator when
# a function needs to not block the UI thread.
def callInNewThread(function):
    def wrappedFunc(*args, **kwargs):
        thread = threading.Thread(target = function, args = args, kwargs = kwargs)
        thread.name = function.__name__
        # Ensure the thread will exit when the program does.
        thread.daemon = True
        thread.start()
    return wrappedFunc


## Call the passed-in function in the main thread once the current queue of
# events is cleared. This is necessary for anything that touches the user
# interface or uses OpenGL. We first test if the current thread is the main
# thread to avoid unnecessary requeuing.

def callInMainThread(function):
    def wrappedFunc(*args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            # Already in main thread.
            function(*args, **kwargs)
        else:
            # Push call to main thread.
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
