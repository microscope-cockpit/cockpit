.. Copyright (C) 2018 University of Oxford

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

Development
###########

GUI Development
===============

UI element considerations
-------------------------

Fundamental requirements
````````````````````````

a. Safety is critical

   For controls that set parameters like live laser powers or motor
   step sizes, it is critical to safety that a control reflects the
   currently used parameter when it is not being used to change that
   parameter.  This is not a trivial matter to achieve: as long as a
   control has focus, it may show an incomplete entry that does not
   reflect the current state.  A solution may be a timeout for data
   entry where, after a fixed period of time, the control relinquishes
   focus and resets to its previous value.

b. Changes must only be committed by affirmative action

   Certain parameters must only be changed by an affirmative action.
   It is common to update control parameters when they lose focus, but
   focus may be lost affirmatively (e.g. by pressing enter or tab), or
   passively (e.g. by clicking elsewhere, or by another window
   stealing focus).  In the passive case, the control may contain
   incomplete, undesirable or even dangerous values, and these should
   not be committed to hardware.  It is not trivial to determine how a
   control lost focus.  The solution may be to assume that focus is
   lost passively, and to only commit values on certain keypresses or
   mouse button actions.

c. Controls should be appropriate

   Sliders and spin controls are only useful when there are both upper
   and lower limits to the range they will control.

d. Controls should be intuitive

   When a slider or spin control range covers more than two decades,
   sliders become less useful: the increment will either be too small
   at the top end, or too large at the bottom end of the scale.  The
   solution is to use log scaling, but this makes the control much
   less intuitive.

e. Transient values should be ignored

   The value of sliders and spin controls can be changed by several
   methods.  A slider can be dragged to a new position; the new
   position is set when the mouse button is released.  Alternatively,
   sliders and spinners can be moved with the scroll wheel or cursor
   keys.  In this case, it is not clear whether the value after a
   scroll or keypress event is the final target, or some transient
   value between old and new targets.  This is problematic where
   parameter updates involve a high-latency step: in such cases,
   transient values should be ignored. Possible solutions:

   1. tied in with point (b): the solution may be to assume that all
      actions are passive until an affirmative enter, tab or click is
      received;

   2. alternatively, the control could be considered 'settled' after a
      sufficient time has elapsed since the last change.

Consequences of requirements
````````````````````````````

Points (c) and (d) make sliders and spinners unsuitable for exposure
times: currently, we can not query the maximum exposure time for all
hardware; where we can, we end up with ranges from sub-millisecond to
tens of seconds.

Sliders and spinners are only suitable for controlling laser powers if
solution (e-1) is implemented.  (e-2) would introduce latency before a
change is committed to the hardware, and latency on these changes is
already high due to slow comms with certain hardware.

Currently, we control both laser powers and exposure times with
buttons that present a menu of suitable values, with a final menu
entry that opens a dialog for entering custom values.  This meets the
requirements in (b), (c), and (d), and avoids the issues outlined in
(e).  The behaviour is much like a ComboBox, but a ComboBox has the
advantage that custom values can be entered directly.  However, it has
a disadvantage similar to point (e): it is possible to scroll through
ComboBox entries using the mouse wheel or cursor keys, but it is not
straightforward to determine whether a value was selected directly (by
clicking on it with the mouse), or it was selected as a transient
value via cursor-key or mousewheel scrolling en route to another
value.  Direct selections need to be acted upon; transients must be
ignored to avoid generating high-latency comms traffic.

A complete but highly redundant solution would be to double up
controls, so that each parameter has a control to set its value, and a
display that shows the parameter's current state.  This could result
in a very cluttered interface, though. (In some cases, this might even
become three controls, as we would show the current set point, and
current actual value).
