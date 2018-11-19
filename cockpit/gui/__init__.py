#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

import pkg_resources

import cockpit.events

import wx


## The resource_name argument for resource_filename is not a
## filesystem filepath.  It is a /-separated filepath, even on
## windows, so do not use os.path.join.

FONT_PATH = pkg_resources.resource_filename(
    'cockpit',
    'resources/fonts/UniversalisADFStd-Regular.otf'
)

BITMAPS_PATH = pkg_resources.resource_filename(
    'cockpit',
    'resources/bitmaps/'
)


## XXX: Still unsure about this design.  There's a single event type
## for all cockpit.events which means we can't easily pass the data
## from those events.  But having a new wx event for each of them
## seems overkill and cause more duplication.
EVT_COCKPIT = wx.PyEventBinder(wx.NewEventType())

class CockpitEvent(wx.PyEvent):
    def __init__(self):
        super(CockpitEvent, self).__init__()
        self.SetEventType(EVT_COCKPIT.typeId)


class EvtEmitter(wx.EvtHandler):
    """Receives :mod:`cockpit.events` and emits a custom :class:`wx.Event`.

    GUI elements must beget instances of :class:`EvtEmitter` for each
    cockpit event they are interested in subscribing, and then bind
    whatever to :const:`EVT_COCKPIT` events.  Like so::

      abort_emitter = cockpit.gui.EvtEmitter(window, cockpit.events.USER_ABORT)
      abort_emitter.Bind(cockpit.gui.EVT_COCKPIT, window.OnUserAbort)

    This ensures that cockpit events are handled in a wx compatible
    manner.  We can't have the GUI elements subscribe directly to
    :mod:`cockpit.events` because:

    1. The function or method used for subscription needs to be called
    on the main thread since wx, like most GUI toolkits, is not thread
    safe.

    2. unsubscribing is tricky.  wx objects are rarely destroyed so we
    can't use the destructor.  Even :meth:`wx.Window.Destroy` is not
    always called.

    """
    def __init__(self, parent, cockpit_event_type):
        assert isinstance(parent, wx.Window)
        super(EvtEmitter, self).__init__()
        self._cockpit_event_type = cockpit_event_type
        cockpit.events.subscribe(self._cockpit_event_type,
                                 self._EmitCockpitEvent)

        ## Destroy() is not called when the parent is destroyed, see
        ## https://github.com/wxWidgets/Phoenix/issues/630 so we need
        ## to handle this ourselves.
        parent.Bind(wx.EVT_WINDOW_DESTROY, self._OnParentDestroy)

    def _EmitCockpitEvent(self, *args, **kwargs):
        self.AddPendingEvent(CockpitEvent())

    def _Unsubscribe(self):
        cockpit.events.unsubscribe(self._cockpit_event_type,
                                   self._EmitCockpitEvent)

    def _OnParentDestroy(self, event):
        self._Unsubscribe()

    def Destroy(self):
        self._Unsubscribe()
        return super(EventHandler, self).Destroy()
