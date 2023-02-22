.. Copyright (C) 2022 Ian Dobbie <ian.dobbie@jhu.edu>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

.. _extending_cockpit:

Extending Cockpit for local setups
**********************************

In general it is hoped that the functionality implemented in cockpit
will be sufficient for most setups, however it is also rather easy to
extend cockpit with local customization's that extend the functionality
for specific use cases.

Most dynamic actions within cockpit result in the emission of specific
events. Examples of this are the arrival of a new camera image, the
change in state of an input line, or the movement of the stage. These
events can be subscribed to in order to trigger specific actions on
the firing of a specific event. The following code will subscribe to
the input signal change and take a snap image when that occurs.

This code could be directly run in the python shell window. This first
imports some essential libraries then defines a function that will be
triggered on the DIO_INPUT event and checks to see if line 3 has
become True, if so it snaps an image with the currently active
cameras.

.. code-block:: python

    from cockpit import events
    import wx
    
    def trigger_event(line,state):
        if (line==3 and state==True):
	    wx.GetApp().Imager.takeImage()
   
    events.subscribe(events.DIO_INPUT,trigger_event)

This is a simple example, and a more involved setup which identifies
nuclei in snapped images and then adds their position to a marked
point list for later followup is contained in the microscope-cockpit
paper
