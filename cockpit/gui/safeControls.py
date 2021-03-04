#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
##
## This is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This software is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

""" safeControls

This module provides a number controls for safe control of devices.

Safe controls aim to mitigate safety issues when controlling hardware that
can present hazards, e.g. lasers. Safe controls:
  * make a clear distinction between their use to display the current state
  of the hardware, and their use to change that state;
  * make a clear distinction between values that should be committed to hardware,
  and values that are generated during the input process and may be transient;
  * only indicate that values should be committed on an affirmative action;
  * if they can only show a single value, fall back to the last committed value
  on loss of focus.
"""

import copy
import wx
import wx.lib.delayedresult as delayedresult
from cockpit.gui.guiUtils import FloatValidator

import wx.lib.newevent

SafeControlCommitEvent, EVT_SAFE_CONTROL_COMMIT = wx.lib.newevent.NewCommandEvent()
SafeControlPendingEvent, EVT_SAFE_CONTROL_PENDING = wx.lib.newevent.NewEvent()


class SafeControl():
    """A base class for safe controls.

    Clients should bind actions to SafeControlCommit events.
    """

    def PostEvent(self, cancel=False):
        """Post an event to signal pending or committed value change.

        Args:
          cancel (Bool): A flag indicating that input was cancelled.
        """
        if cancel or self._pending is not None:
            evt = SafeControlPendingEvent(id=self.GetId(), Value=self._pending)
        elif self.Value is not None:
            evt = SafeControlCommitEvent(id=self.GetId(), Value=self.Value, Commit=True)
        else:
            return
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

    def SetPending(self, pending=None):
        """Set the pending value.

        Args:
          pending: The value, as an int, float or string.

        If pending is not None, the current display does not reflect the real
        state, so the control is highlighted.
        If pending is None, the value has been committed and the display reflects
        the actual state, so the highlight is cleared.
        """
        if pending is None:
            self._pending = None
            self.SetBackgroundColour(wx.NullColour)
            self.Value = self._committed
        else:
            try:
                self._pending = float(pending)
            except:
                pass
            self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT))

    def Cancel(self):
        """Cancel - resets to last committed value."""
        if self._pending is not None:
            self.SetValue(self._committed)
            self.PostEvent(cancel=True)

    def Commit(self):
        """Commit the pending value."""
        if self._pending is None:
            return
        self.SetValue(self._pending)
        self.PostEvent()

    def SetValue(self, value):
        """Commits a value and updates the displayed value.

        Args:
          value: The value, as an int, float or float-parsable string.
        """
        self.Value = value
        self._committed = value
        self.SetPending(None)
        self.Refresh()

    def ReleaseFocus(self):
        p = self.GetParent()
        while not p.AcceptsFocus():
            p = p.GetParent()
        p.SetFocus()


class SafeSpinCtrlDouble(SafeControl, wx.Panel):
    """A cross-platform spin control for double-precision floats.

    wx.SpinCtrlDouble is implemented in C++, with very different
    implementations and behaviour (particularly relating to events)
    across platforms. This class uses a TextCtrl and SpinButton to
    achieve the same behaviour across Mac, Linux and MSWin platforms.
    """

    def __init__(self, *args, minValue=0, maxValue=float('inf'), inc=0.2, value=0, **kwargs):
        """Initialise a SafeSpinCtrlDouble

        Args:
          *args:  Variable-length arguments list.

        Kwargs:
          minValue (float): The minimum allowable value.
          maxValue (float): The maximum allowable value
          inc (float): The increment for value changes.
          value  (float): The initial value
          **kwargs: arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self._pending = None
        self._min = minValue
        self._max = maxValue
        self._inc = inc
        self._committed = None
        self._checkTimer = wx.Timer(self)
        if str(inc).find('.') != -1:
            self._places = len(str(inc)) - str(inc).find('.') - 1
        else:
            self._places = 0
        te = self.te = wx.TextCtrl(self)
        if 'size' in kwargs:
            self.te.SetInitialSize(kwargs.get('size'))
        else:
            longest = max(map(len, (str(minValue), str(maxValue)))) + self._places + 2
            self.te.SetInitialSize(te.GetSizeFromTextSize(te.GetTextExtent(longest * "0" + "-.")))
        self.te.SetValidator(FloatValidator())
        sb = wx.SpinButton(self)
        self.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.Sizer.Add(self.te, proportion=1)
        self.Sizer.Add(sb, proportion=0)
        self.Fit()
        sb.MaxSize = (-1, te.Size[-1])
        # initialise _committed
        self.SetValue(value)
        # initialise text control
        self.te.SetValue(str(value))
        # Pass background colour to the text control.
        self.SetBackgroundColour = self.te.SetBackgroundColour
        # Set up the SpinButton
        sb.SetRange(0, 2)
        sb.Value = 1
        self.Bind(wx.EVT_SPIN, self.OnSpin)

        self.Bind(wx.EVT_CHAR_HOOK, self.OnChar)
        self.Bind(wx.EVT_TEXT, self.OnText)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)

        # Use a timer to check control still has focus.
        self.Bind(wx.EVT_TIMER, self.CheckFocus)
        self.Bind(wx.EVT_SET_FOCUS, self.GetParent().SetFocus)
        self.Bind(wx.EVT_CHILD_FOCUS, self.OnFocus)
        self.Bind(wx.EVT_KILL_FOCUS, lambda evt: self.Cancel())
        self.AcceptsFocusRecursively = lambda: True
        self.AcceptsFocus = lambda: False

    def OnFocus(self, evt):
        """Start the timer that detects loss of focus.

        Args:
          evt: A wx.EVT_SET_FOCUS or wx.EVT_CHILD_FOCUS event.
        """
        if not self._checkTimer.IsRunning():
            self._checkTimer.StartOnce(500)

    def CheckFocus(self, evt):
        """Ensure this control displays committed values when it loses focus.

        Args:
          evt (wx.TimerEvent): The event.

        On some platforms, TextEntry controls do not reliably receive
        EVT_KILL_FOCUS events when they lose focus, so we use a timer to check
        focus periodically.
        """
        if self._pending is not None and not (self.HasFocus() or self.te.HasFocus()):
            self.Cancel()
        else:
            self._checkTimer.StartOnce(500)

    def OnMouseWheel(self, evt):
        """Update value and apperance on mouse scroll.

        Args:
          evt (wx.MouseEvent): The event.
        """
        if evt.WheelRotation > 0:
            new_val = self.Value + self._inc
        elif evt.WheelRotation < 0:
            new_val = self.Value - self._inc
        else:
            return
        self.te.SetFocus()
        new_val = max(min(new_val, self._max), self._min)
        self.SetPending(new_val)
        self.PostEvent()

    def OnSpin(self, evt):
        """Update value and appearnace on spin button event.

        Args:
          evt (wx.SpinEvent): The event.
        """
        self.te.SetFocus()
        if evt.Position == 0:
            new_val = self.Value - self._inc
        elif evt.Position == 2:
            new_val = self.Value + self._inc
        else:
            return
        new_val = max(min(new_val, self._max), self._min)
        self.SetPending(new_val)
        evt.EventObject.Value = 1
        self.PostEvent()

    def OnText(self, evt):
        """Update value and appearance on validated text input

        Args:
          evt (wx.CommandEvent(wx.wxEVT_TEXT)): The event.
        """
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT))
        if evt.String in ['', '.', '-']:
            return
        text = self.GetValue()
        self.SetPending(text)
        self.PostEvent()

    def OnChar(self, evt):
        """Handle character events.

        This function just routes keypresses to different behaviours; input
        validation is carried out elsewhere.

        Args:
          evt (wx.KeyEvent): The event.
        """
        self._laststr = self.te.GetValue()
        if evt.KeyCode == wx.WXK_ESCAPE:
            # Cancel on escape
            self.Cancel()
            wx.CallAfter(self.ReleaseFocus)
        elif evt.KeyCode in [wx.WXK_NUMPAD_ENTER, wx.WXK_RETURN, wx.WXK_SPACE,
                             wx.WXK_NUMPAD_TAB, wx.WXK_TAB]:
            if self._laststr != '':
                # Commit on return, enter, space or tab
                self._pending = min(max(self.Value, self._min), self._max)
                self.Commit()
            if evt.KeyCode != wx.WXK_TAB:
                wx.CallAfter(self.ReleaseFocus)
            evt.Skip()
        elif evt.KeyCode in [wx.WXK_UP, wx.WXK_NUMPAD_UP]:
            # Up arrows increment value
            self.SetPending(self.Value + [1, 10][evt.shiftDown] * self._inc)
            self.PostEvent()
        elif evt.KeyCode in [wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN]:
            # Down arrows decrement value
            self.SetPending(self.Value - [1, 10][evt.shiftDown] * self._inc)
            self.PostEvent()
        else:
            evt.Skip()

    @property
    def Value(self):
        """Return currently displayed value; fallback to last committed value.

        Returns:
          float: The currently displayed value, with fallback to the last
            committed value and, finally, last pending value.
        """
        try:
            return float(self.GetValue())
        except:
            return self._committed if self._pending is None else self._pending

    @Value.setter
    def Value(self, value):
        """Set the currently display value.

        Args:
          value: The value to display as a string, int or float.
        """
        if value is not None and (self.Value != value):
            s = str(value)
            if '.' in s:
                s = s[:s.find('.') + self._places + 1]
            self.te.ChangeValue(s)

    def SetPending(self, pending):
        """Handle updates to the pending value.

        Args:
          pending (string): The new pending value as a string.
        """
        # Reset the focus-check timer.
        self._checkTimer.StartOnce(500)
        super().SetPending(pending)
        if self._pending is not None and not self.HasFocus():
            self.Value = self._pending
        if pending is None:
            self.te.SetSelection(0, 0)

    def GetValue(self):
        """Return the currently displayed value.

        Returns:
          string: The currently displayed value.
        """
        return self.te.GetValue()


class GaugeValue():
    """Parameters used to display values on a gauge, with or without set point."""

    def __init__(self, value=0, minVal=0, maxVal=100, tol=0.01, fetch=None):
        """Create a GaugeValue

        Kwargs:
          value (float): An initial value.
          minVal (float): The minimum allowed value.
          maxVal (float): The maximum allowed value.
          tol (float): A tolerance used to compare current value and a set point.
          fetch (function): A function to fetch the current value from some source.
        """

        self.min = minVal
        self.max = maxVal
        self.setpoint = value
        self.tol = tol
        self.fetch = fetch
        # The last observed value.
        self.last = None

    @property
    def range(self):
        """Return the range of the GaugeValue."""
        return self.max - self.min

    def to_quotient(self, value=None):
        """Convert a value to a quotient of the GaugeValue range.

        Kwargs:
          value (float or None): A value to convert or None to convert current setpoint.

        Returns:
          float: The value or current setpoint as a fraction of the gauge range.
        """
        if value is None:
            value = self.setpoint
        return (value - self.min) / (self.max - self.min)

    def from_quotient(self, quot):
        """Convert a quotient of the GaugeValue range to a value.

        Args:
          quot (float): The quotient.

        Returns:
          float: The value represented at the point quot into the mapped range.
        """
        return self.min + quot * (self.max - self.min)

    def on_target(self):
        """Test if the last fetched value is on target.

        Returns:
          bool: Whether or not the last fetched value is within tol of the setpoint."""
        if self.last is None:
            return True
        return abs(self.last - self.setpoint) / (self.range) < self.tol


class SetPointGauge(SafeControl, wx.Window):
    """A gauge that tracks a parameter against a set-point."""
    # A mapping of elements to wx.Colour instances, populated by first instance.
    colours = {}

    def __init__(self, parent, id=wx.ID_ANY,
                 tolerance=.005, minValue=0, maxValue=100,
                 fetch_current=None, margins=wx.Size(0, 3),
                 pos=wx.DefaultPosition, size=(-1, 18), style=wx.SL_HORIZONTAL):
        """Initialise a SetPointGauge

        Args:
          parent (wx.Window): the parent window

        Kwargs:
          id (int): A wx ID.
          tolerance (float): The tolerance for checking value against setpoint.
          minValue (float): The minimum allowable value.
          maxValue (float): The maximum allowable value.
          fetch_current (function): A function to fetch the current value.
          margins (wx.Size): The horizontal and vertical margins.
          pos (wx.Position): The window position.
          size (wx.Size): The window size.
          style: A combination of wx WindowStyle flags.
        """
        if len(self.__class__.colours) == 0:
            # initialise colours
            self.__class__.colours.update({
                'setpoint': wx.Colour('yellow'),
                'black': wx.Colour('black'),
                'on_target': wx.Colour((127,255,0,255)), # chartreuse
                'off_target': wx.Colour('firebrick'),
                'scale': wx.Colour('cyan'),
                'needle': wx.Colour('magenta')})

        wx.Window.__init__(self, parent, id, pos, size, style)
        self._value = GaugeValue(50, minValue, maxValue, tolerance, fetch_current)
        self._fetching = False
        self._vertical = style & wx.SL_VERTICAL > 0
        if self._vertical:
            self.MinSize = (18, 96)
            self.Size = (18, -1)
        else:
            self.MinSize = (96, 18)
            self.Size = (-1, 18)
        self._anim = []
        self._displayed = self._value.setpoint
        self._pending = None
        self.SetValue(self.Value)  # initialises _committed

        self._timer = wx.Timer(self)
        self._timer.Start(50)

        self._margins = margins

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_TIMER, self.OnTimer)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLDClick)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnDrag)
        self.AcceptsFocusFromKeyboard = lambda: False
        self.SetDoubleBuffered(True)

    @property
    def Value(self):
        return self._value.setpoint

    @Value.setter
    def Value(self, value):
        """
        Sets the current set point of a SetPointGauge in mapped units.

        Args:
          value (float): A float in mapped units specifying the current set point.
        """
        delta = value - self._displayed
        nsteps = int(min(10, abs(delta) // (0.01 * self._value.range)))
        self._anim = [self._displayed + i * delta / nsteps for i in range(nsteps)]
        self._anim.append(value)
        self._anim.reverse()
        self._value.setpoint = value

    def GetValue(self):
        """Return the current setpoint.

        Returns:
          float:  The current setpoint."""
        return self._value.setpoint

    def PosToValue(self, pos):
        """Convert a gauge position to mapped value.

        Args:
          pos (wx.Position): The position, e.g. from a mouse click.

        Returns:
          float: The value represented at point pos in the gauge range.
        """
        rect = self.GetClientRect()
        if self._vertical:
            return self._value.from_quotient((rect.height - pos[1]) / rect.Size[1])
        else:
            return self._value.from_quotient(float(pos[0] / rect.Size[0]))

    def ValueToPos(self, value):
        """Convert a mapped value to a gauge position.

        Args:
          value (float): The value to convert.

        Returns:
          float: The fraction into the range at which value is represented.
        """
        rect = self.GetClientRect()
        if self._vertical:
            return self._value.to_quotient(value) * rect.Size[1]
        else:
            return self._value.to_quotient(value) * rect.Size[0]

    def OnDrag(self, evt):
        """Handle drag events.

        Updates pending value based on mouse position, issues events to update
        linked controls, and cancels on dragging beyond the limits of the gauge.

        Args:
          evt (wx.MouseEvent): The drag event.
        """
        pos = evt.GetLogicalPosition(wx.ClientDC(self))
        if evt.Dragging() and evt.LeftIsDown() and self.GetClientRect().Contains(pos):
            self.SetPending(self.PosToValue(pos))
            self.PostEvent()
        elif evt.LeftUp():
            self.Commit()
        elif evt.Leaving() and self.HasFocus():
            self.Cancel()
        evt.Skip()

    def OnLDClick(self, evt):
        """Handle double-click events.

        Args:
          evt (wx.MouseEvent): The double-click event.
        """
        pos = evt.GetPosition()
        self.SetPending(self.PosToValue(pos))
        self.Commit()

    @property
    def range(self):
        """The magnitude of the range represented by the gauge.the

        Property synonym for GetRange().

        Returns:
          float: The gauge range.
        """
        return self.GetRange()

    def GetRange(self):
        """Retruns the range of a SetPointGauge value like a wx.Slider.

        Returns:
          float: The gauge range.
        """
        rect = self.GetClientRect()
        return (0, [rect.width, rect.height][self._vertical])

    def SetFetchCurrent(self, f):
        """
        Sets the the function used to poll a SetPointGauge value.

        Args:
          f (function): a function with no arguments that returns a float.
        """
        self._value.fetch = f

    def SetTolerance(self, value):
        """
        Sets the tolerance of a SetPointGauge value in mapped units.

        Args:
          value (float): the tolerance as a fraction of the gauge range.
        """
        self._value.tol = value

    def OnPaint(self, evt):
        """
        Handles the ``wx.EVT_PAINT`` event for :class:`SetPointGauge`.

        Args:
          event (wx.PaintEvent): The PaintEvent to be processed.
        """
        dc = wx.BufferedPaintDC(self)
        c = self.__class__.colours
        rect = self.GetClientRect()
        gradient = [wx.EAST, wx.NORTH][self._vertical]

        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        dc.SetPen(wx.Pen(wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUHILIGHT)))
        bar = copy.copy(rect)
        if self._vertical:
            bar.width -= 2 * self._margins[1]
            bar.X += self._margins[1]
            bar.height = rect.height * self._value.to_quotient(self._displayed) - 2 * self._margins[0]
            bar.Y = rect.height - bar.height + self._margins[0]
        else:
            bar.height -= 2 * self._margins[1]
            bar.Y += self._margins[1]
            bar.width = rect.width * self._value.to_quotient(self._displayed) - 2 * self._margins[0]
            bar.X += self._margins[0]
        dc.SetBrush(wx.Brush(c['setpoint']))
        dc.SetPen(wx.Pen(c['setpoint']))
        dc.GradientFillLinear(bar, c['black'], c['setpoint'], gradient)

        # Draw the current value
        bar = copy.copy(rect)
        if self._value.fetch is None:
            current = self._displayed
        else:
            current = self._value.last
        if self._vertical:
            bar.height = rect.height * self._value.to_quotient(current)
            bar.Y = rect.height - bar.height
            bar.width = rect.width // 3
            bar.X += (rect.width // 2) - (bar.width // 2)
        else:
            bar.width = rect.width * self._value.to_quotient(current)
            bar.height = rect.height // 3
            bar.Y += (rect.height // 2) - (bar.height // 2)
        colour = c['on_target'] if self._value.on_target() else c['off_target']
        dc.SetBrush(wx.Brush(colour))
        dc.SetPen(wx.Pen(colour))
        dc.DrawRectangle(bar)

        self.DrawLimitIndicators(dc)

        # Draw a scale
        dg = 0
        n = 40
        while dg < 16:
            n = n // 2
            dg = rect.Size[self._vertical] / n
        if self._vertical:
            lines = [(2, min(rect.height - 1, i * dg), rect.width - 2,
                      min(rect.height - 1, i * dg)) for i in range(1, n)]
        else:
            lines = [(min(rect.width - 1, i * dg), 2, min(rect.width - 1, i * dg),
                      rect.height - 2) for i in range(1, n)]
        dc.SetPen(wx.Pen(colour=c['scale'], width=1, style=wx.PENSTYLE_DOT))
        dc.DrawLineList(lines)

        # Draw any pending value.
        if self._pending is not None:
            pen = wx.Pen(colour=c['needle'], width=3)
            pen.SetCap(wx.CAP_ROUND)
            dc.SetPen(pen)
            pos = self._value.to_quotient(self._pending)
            if self._vertical:
                pos = rect.height * (1 - pos)
                dc.DrawLine(0, pos, rect.width, pos)
            else:
                pos *= rect.width
                dc.DrawLine(pos, 0, pos, rect.height)

    def DrawLimitIndicators(self, dc):
        """Draws <<< or >>> to indicate values exceeeding gauge range.

        Args:
          dc (wx.DeviceContext): The device context to use for drawing.
        """
        rect = self.GetClientRect()

        dirn = None
        if self._value.last is None:
            return

        if self._value.last < self._value.min:
            dirn = -1
        elif self._value.last > self._value.max:
            dirn = 1
        else:
            return

        if self._vertical:
            dirn *= -1

            def f_ch(pos, dirn):
                mid = rect.width // 2
                return [(mid, pos, 0, pos - dirn * mid),
                        (mid, pos, rect.width, pos - dirn * mid)]
        else:
            def f_ch(pos, dirn):
                mid = rect.height // 2
                return [(pos, mid, pos - dirn * mid, 0),
                        (pos, mid, pos - dirn * mid, rect.height)]

        if dirn is not None:
            dc.SetPen(wx.Pen(self.__class__.colours['on_target'], width=2))

            posns = [self.range[dirn == 1] - i * dirn * 6 for i in range(3)]
            [dc.DrawLineList(f_ch(pos, dirn)) for pos in posns]

    def OnTimer(self, evt):
        """Handle the wx.EVT_TIMER event for :class:`SetPointGauge`.

        Args:
          evt (wx.TimerEvent): The TimerEvent to be processed.
        """
        if self._value.fetch and not self._fetching:
            delayedresult.startWorker(self._onFetch, self._value.fetch, wargs=())
            self._fetching = True
        if self._anim:
            self._displayed = self._anim.pop()
        self.Refresh()

    def _onFetch(self, result):
        """A callback to process the result of a call to self._value.fetch.

        Args:
          result (wx.lib.delayedresult.DelayedResult): The result to process.
        """
        try:
            self._value.last = result.get()
        except:
            self._value.last = None
        self._fetching = False


class SpinGauge(wx.Panel):
    """A combined gauge and spin control."""

    def __init__(self, parent, minValue=0, maxValue=100, increment=None, fetch_current=None):
        """Initialise a SpinGauge

        Args:
          parent (wx.Window): the parent window

        Kwargs:
          minValue (float): The minimum allowable value.
          maxValue (float): The maximum allowable value.
          increment (float): The base value increment.
          fetch_current (function): A function to fetch the current value.
          pos (wx.Position): The window position.
          size (wx.Size): The window size.
          style: A combination of wx WindowStyle flags.
        """
        super().__init__(parent=parent, id=wx.ID_ANY)
        # Determine increment
        increment = increment or float("%1.g" % ((maxValue - minValue) / 1000))

        spinner = SafeSpinCtrlDouble(parent=self, id=wx.ID_ANY,
                                     minValue=float(minValue), maxValue=float(maxValue), inc=increment)
        slider = SetPointGauge(self, minValue=minValue, maxValue=maxValue, fetch_current=fetch_current)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(spinner, flag=wx.EXPAND)
        sizer.Add(slider, flag=wx.EXPAND)

        self.SetSizerAndFit(sizer)
        self.controls = set([spinner, slider])
        self.spinner = spinner
        self.slider = slider
        self._value = 0

        # If a child control's value changes, it must notify other controls.
        # We make bindings to each child control for this, so that a client
        # using this control can bind its own action to value changes.
        # Pending changes and committed changes are handled as separate events
        # so that the client can bind a simple actions to handle each case
        # separately.
        for c in self.controls:
            c.Bind(EVT_SAFE_CONTROL_PENDING, self.ChildOnSafeControlEvent)
            c.Bind(EVT_SAFE_CONTROL_COMMIT, self.ChildOnSafeControlEvent)
        self.Bind(wx.EVT_SET_FOCUS, self.GetParent().SetFocus)
        self.AcceptsFocus = lambda: False

    def ChildOnSafeControlEvent(self, evt):
        """Handle child control value change events and update other controls.

        Args:
          evt: The SafeControlPendingEvent or SafeControlCommitEvent to handle.
        """
        others = self.controls.difference([evt.GetEventObject()])
        isCommit = isinstance(evt, SafeControlCommitEvent)
        for other in others:
            if isCommit:
                other.SetValue(evt.Value)
            else:
                other.SetPending(evt.Value)
        if isCommit:
            evt.Skip()  # Propogate up so self can handle commit events.

    @property
    def Value(self):
        """A property synonym for GetValue.

        Returns:
          float: The current value of the control.
        """
        return self._value

    @Value.setter
    def Value(self, value):
        """Set the value displayed on child controls.

        Args:
          value: The new value as a float, int or float-parsable string.
        """
        self.SetValue(value)

    def GetValue(self):
        """Get the current value.

        Returns:
          float: The current value of the control
        """
        return self._value

    def SetValue(self, value):
        """Set the value displayed on child controls.

        Args:
          value: The new value as a float, int or float-parsable string.
        """
        self._value = value
        self.slider.SetPending(None)
        for obj in self.controls:
            obj.SetValue(value)

