This directory contains the code that actually talks to hardware devices to
control the microscope. If you want to add new hardware, this is the place 
to start. Make a new module, ensure it subclasses the Device class in 
device.py, and then start filling in the functions that the Device class 
requires.
