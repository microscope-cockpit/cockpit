This directory contains code that "controls" simulated devices. The idea here
is that you can get the cockpit up and running without actually having any 
hardware hooked up to it, by just using these simulated devices. Then you can
replace them piecemeal with actual hardware control. 

camera.py: Generates test patterns.

device.py: Standard copy of the Device class module.

drawer.py: Pretend "drawer" that makes up wavelengths for the "cameras" it 
  controls. You'll need to modify this at the same time that you replace the 
  camera control code.
  
executor.py: Dummy experiment execution code.

imager.py: Dummy imaging code.

lights.py: Dummy light sources.

mover.py: Dummy stage positioner.

objective.py: Dummy objectives.

server.py: Same copy of the server code that everything else uses. 
