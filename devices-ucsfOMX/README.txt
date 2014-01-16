This directory contains the code that controls hardware for the OMX microscope.

configurator.py: Basic configuration: where to save data, what the "slide" and
  "dish" altitudes are, etc.
  
deepstar.py: Communications with the Deepstar laser control systems running 
  on the "drill" computer. 
  
delayGen.py: Communications with the digital delay generator, over Ethernet. 

device.py: Basic copy of the Device class module. 

drawer.py: Describes the filters in front of each camera. 

dsp.py: Communicates with the DSP control code running on the "dsp" computer. 
  Sends digital TTL signals to our lights and cameras (and to the delay 
  generator), controls the piezo stage positioners, and adjusts the SI phase 
  piezo. 

filterWheel.py: Communicates with the filter wheel serial proxy code running
  both on the "omx-cockpit" computer (488) and on the "drill" computer
  (global and 560). 

irRemote.py: Handles communications with the infrared remote control via
  a serial port. 
  
ixonCameras.py: Communicates with the camera control software on the 
  "cam-1u1", "cam-1u2", "cam-1u3", and "cam-ultra" computers, which control
  our EMCCD cameras. If you want to know which camera is which computer, check
  the stickers on the computers.
  
nanomover.py: Communicates with the Nanomover stage positioning software 
  running on the "nano" computer. 
  
ni435x.py: Communicates with the NI435x software running on the "nano" 
  computer, which in turn controls: the light path mirror flips; the
  temperature sensors; the room light sensor.

objective.py: Provides a selection of objectives and associated pixel sizes.

powerButtons.py: Communicates with the serial boot bar control program running
  on the "omx-cockpit" computer, which provides power to lasers, the diffuser
  wheel, and the fiber shaker. 

rotationStage.py: Communicates with the rotation stage control code running on
  the "nano" computer. The rotation stage is used in SI experiments. 
  
server.py: Standard copy of the server code used to allow other programs to
  send information to the cockpit.
