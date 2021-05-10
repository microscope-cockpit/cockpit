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

"""This package contains all the UI for Cockpit.

All of the widgets that are not created by specific devices live here
--- the mosaic, macro stage view, camera window, etc.  The different
GUI windows and widgets automatically adjust themselves based on the
number and capabilities of the hardware available.

Some of subpackages are:

- :mod:`cockpit.gui.camera`: handles the display of images received
  from the camera(s).  It depends heavily on the
  :mod:`cockpit.gui.imageViewer`.

- :mod:`cockpit.gui.dialogs`: contains all dialog subclasses and any
  widgets that are specific to them.  This includes the experiment
  setup dialogs.

- :mod:`cockpit.gui.imageViewer`: generic code for displaying pixel
  arrays to the screen.  It includes a histogram for black/white
  scaling, zoom and drag, etc.

- :mod:`cockpit.gui.macroStage`: the Macro Stage window gives the user
  a high-level overview of where they are with respect to the motion
  limits of their stage.

- :mod:`cockpit.gui.mosaic`: the mosaic provides a UI to map out the
  user's sample in detail.  It consists of a large OpenGL canvas and
  some associated buttons.

And some of its modules are:

- :mod:`cockpit.gui.fileViewerWindow`: displays MRC files; this code
  is invoked when an MRC file is dragged onto the main window.

- :mod:`cockpit.gui.guiUtils`: utility functions for setting up and
  running the UI.

- :mod:`cockpit.gui.keyboard`: binds keyboard shortcuts to windows.

- :mod:`cockpit.gui.loggingWindow`: displays standard output and
  standard error.

- :mod:`cockpit.gui.mainWindow`: shows exposure settings, the
  run-experiment buttons, and any custom UI created by device code.

"""


import sys
import traceback

import pkg_resources
import wx
import wx.lib.newevent

import cockpit.events


## The resource_name argument for resource_filename is not a
## filesystem filepath.  It is a /-separated filepath, even on
## windows, so do not use os.path.join.

IMAGES_PATH = pkg_resources.resource_filename(
    'cockpit',
    'resources/images/'
)


## A single event type for all cockpit.events. The origian cockpit
## event data is passed back as CockpitEvent.EventData.
CockpitEvent, EVT_COCKPIT = wx.lib.newevent.NewEvent()


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
        super().__init__()
        self._cockpit_event_type = cockpit_event_type
        cockpit.events.subscribe(self._cockpit_event_type,
                                 self._EmitCockpitEvent)

        ## Destroy() is not called when the parent is destroyed, see
        ## https://github.com/wxWidgets/Phoenix/issues/630 so we need
        ## to handle this ourselves.
        parent.Bind(wx.EVT_WINDOW_DESTROY, self._OnParentDestroy)

    def _EmitCockpitEvent(self, *args, **kwargs):
        self.AddPendingEvent(CockpitEvent(EventData=args))

    def _Unsubscribe(self):
        cockpit.events.unsubscribe(self._cockpit_event_type,
                                   self._EmitCockpitEvent)

    def _OnParentDestroy(self, event):
        self._Unsubscribe()
        event.Skip()

    def Destroy(self):
        self._Unsubscribe()
        return super().Destroy()


def ExceptionBox(caption="", parent=None):
    """Show python exception in a modal dialog.

    Creates a modal dialog without any option other than dismising the
    exception information.  The exception traceback is displayed in a
    monospaced font and its text can be copied into the clipboard.

    This only works during the handling of an exception since it is
    not possible to retrieve the traceback after the handling.

    Args:
        caption (str): the dialog title.
        parent (wx.Window): parent window.
    """
    current_exception = sys.exc_info()[1]
    if current_exception is None:
        raise RuntimeError('Not handling an exception')

    ## wx.MessageDialog looks better than plain wx.Dialog but we want
    ## to include the traceback without line-wrapping and to be able
    ## to copy its text.  We can't easily reimplement wx.MessageDialog
    ## with this extras because wx.MessageDialog is not a simple
    ## subclass of wx.Dialog, it uses native widgets for simpler
    ## dialogs, such as gtk_message_dialog_new.

    dialog = wx.Dialog(parent, title=caption, name="exception-dialog",
                       style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
    message = wx.StaticText(dialog, label=str(current_exception))
    details = wx.TextCtrl(dialog, value=traceback.format_exc(),
                          style=(wx.TE_MULTILINE|wx.TE_DONTWRAP|wx.TE_READONLY))

    ## 'w.Font.Family = f' does not work because it 'w.Font' returns a
    ## copy of the font.  We need to modify that copy and assign back.
    details_font = details.Font
    details_font.Family = wx.FONTFAMILY_TELETYPE
    details.Font = details_font

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(message, wx.SizerFlags(0).Expand().Border())
    sizer.Add(details, wx.SizerFlags(1).Expand().Border())
    sizer.Add(dialog.CreateSeparatedButtonSizer(wx.OK),
              wx.SizerFlags(0).Expand().Border())

    ## The default width of a TextCtrl does not take into account its
    ## actual content.  We need to manually set its size (issue #497)
    if (wx.Platform != '__WXMSW__') and (wx.Platform != '__WXMAC__'):
        details_text_size = details.GetTextExtent(details.Value)
    else:
        ## On Windows and Mac, GetTextExtent ignores newlines so we
        ## need to manually compute the text extent.
        traceback_lines = details.Value.splitlines()
        longest_line = max(traceback_lines, key=len)
        one_line_size = details.GetTextExtent(longest_line)
        details_text_size = wx.Size(one_line_size[0],
                                    one_line_size[1] * len(traceback_lines))
    details.SetInitialSize(details.GetSizeFromTextSize(details_text_size))

    dialog.SetSizerAndFit(sizer)
    dialog.Centre()
    dialog.ShowModal()
