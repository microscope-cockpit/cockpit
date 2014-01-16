This directory contains the code used for controlling hardware in the OMXT
microscope. 

configurator.py: some basic configuration; mostly, the location where files 
  are saved to.

delayGen.py: Communications with the digital delay generator, over Ethernet.

device.py: Standard copy of the base Device class module.

drawer.py: Dummy "drawer" that's just used to indicate the wavelengths that
  the cameras see.

dsp.py: Communicates with the DSP card through software on the catinthelab
  computer. Very similar code to that in OMX.

ixonCameras.py: Communicates with the EMCCD control software on 
  the aomicroscope computer. Very similar code to that in OMX.

neoCameras.py: Communicates with the CMOS camera on the "neo"/"zyla" 
  computer. Originally named Neo for Andor's first attempt at a CMOS camera; 
  now we use a Zyla camera instead. 
  
objective.py: Describes the pixel sizes available given our different
  objectives and the fact that the pixel size is subtly different for the EMCCD
  vs. the CMOS.
  
physikInstrumente.py: Controls the PI stage motion control. Two devices: one 
  for XY motion, the other for Z. We control XY through a serial port, and
  the Z piezo through a Telnet proxy. The Z device controller (the physical
  box) can't handle dropped connections, so the proxy is just there to provide
  a consistent connection.
  
server.py: Standard "server" system to let other devices send data to the 
  cockpit.
