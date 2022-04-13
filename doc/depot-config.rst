.. Copyright (C) 2022 Ian Dobbie <ian.dobbie@jhu.edu>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

.. _depot_configuration:

Device Specific Configuration
*****************************

There are a few general configuration parameters and then some device
specific configuration options. The depot file(s) all have an INI
format, with sections defined by square brackets.


Required python-microscope config
`````````````````````````````````

Most cockpit devices will connect to `Python-Microscope
<https://python-microscope.org/>`_ devices. Most of the hardware
specific configuration will be performed in the microscope instance
and shared out over the network via the Microscope device-server. In
this case each device requires a device type and a Pyro URI
definition including name, network address and port number, an example is:

.. code:: ini

  [Testcam]
  type: cockpit.devices.microscopeCamera.MicroscopeCamera
  uri: PYRO:TestCamera@10.1.10.229:8000



Digital hardware trigger configuration
``````````````````````````````````````

As well as these require components, any device with a digital hardware
triggering also requires information about the trigger, eg:

.. code:: ini

  triggerSource: dsp
  triggerLine: 8

In this instance the hardware trigger comes from the device named
'dsp' and utilises digital trigger line 8.

Stages
``````

Stages have some specific requirements. In general stages will require
names for the axis, and scaling information to match stage units to
real world units. Additionally stages also require a movement_time
parameter which accounts for the time of an actual movement and the
time for the system to settle after the movement. For example a 3 axis
stage might have:

.. code:: ini

  type: cockpit.devices.microscopeDevice.MicroscopeStage
  uri: PYRO:stage@localhost:8000
  x-axis-name: x
  y-axis-name: y
  z-axis-name: z
  x-units-per-micron: 1
  y-units-per-micron: 1
  z-units-per-micron: 1
  movement_time: 0.03 0.03


Additionally, stages which are to be used in a synchronous manner with
rapid image stacks, usually Z axis, require either digital or analog
control. These will have a format similar to the trigger lines
above. Analog control is defined by a series of definitions, an
example of an analog z piezo stage is:


.. code:: ini

  [zPiezo]
  type: cockpit.devices.stage.SimplePiezo
  analogSource: dsp
  analogLine: 0
  offset: 0
  gain: 37.2318
  min: 0
  range: 220


Cameras
```````

Cameras have a few additional parameters that can be very useful. The
transform parameter is a tuple, specifying vertical flip, horizontal
flip and rotation. The three Boolean parameters allow any 90 deg
rotation or mirror of the image to be specified. This allows the
camera image orientation to match the users expectation and the stage
XY axes. The wavelength parameter allows specification of a fixed
emission wavelength for images form this camera, alternatively the
filter wheel parameter 'cameras' can be used to specify a motorised
filter wheel which enables selection of different emission wavelengths.

.. code:: ini

  transform: (0, 0, 1)
  wavelength: 610

Filter Wheels
`````````````

Filter wheels allow the modulation of illumination intensity via a
wheel loaded with neutral density filters in the illumination path, or
selection of the emission wavelength via interference filters in front
of a camera.

An emission filter wheel is defined a section like the following:

.. code:: ini

  cameras: camera
  filters:
    0, Blue, 460
    1, Green, 510
    2, Red, 620


This provides an emission filter wheel in front of the device called
'camera' with 3 filters in the specified wheel locations with labels
and emission wavelengths.

An NDfilter wheel in front of a light source, or range of light
sources is defined like: (no idea what the spec for this is need to check)

Executor
````````

The hardware timing is performed by a so called executor device. These
devices need to specify the number of analog and digital control
lines that they provide, for instance with a Red Pitaya single board
computer providing the executor you have a section along the lines of: 

.. code:: ini

  [dsp]
  type: cockpit.devices.executorDevices.ExecutorDevice
  uri: PYRO:redPitaya@192.168.0.20:8005
  dlines: 16
  alines: 2



SI polarizer
````````````

Many of the existing cockpit systems are Structured Illumination
Microscopes (SIM) and utilises LCD based polarization control, which are
driven by analog voltages from the executor. These devices need a
control source, gain and offset. The idle voltage says what voltage to
set the control voltage to during idle times. The SIM configuration
also need angle dependent voltages for each calibrated wavelength, eg:

.. code:: ini

  [SI polarizer]
  type: cockpit.devices.polarizationRotator.PolarizationDevice
  analogSource: dsp
  analogLine: 1
  gain: 1618.171641791
  offset: 0
  siVoltages: 488: 0.58, 0.67, 0.800
              561: 0.500, 0.60, 0.75
  idleVoltage: 1.0

Objectives
``````````

The specification of the objectives are also defined in the depot
configuration file. Each objective has an associated pixel size and
can provide an updated transform which will override the camera
transform. The colour parameter is used to display possibly different
accessible regions from different objectives in the stage and mosaic
views. Additionally, there is an offset parameter which enables
difference between objective fields of view to be accounted for in
stage position. The lensID parameter is stored in image file metadata
fields so can be used to tag specific objectives, or objective types. 

.. code:: ini

  [10x]
  type: cockpit.devices.objective.ObjectiveDevice
  pixel_size: 0.787
  transform:(0, 1, 1)
  offset: (-34894, 320,-5955)
  colour:(1,0,0)
  lensID: 10118

    
  
Additional specific parameters
``````````````````````````````

As well as the general parameters defined by the different microscope
device types, hardware specific parameters can be set and any not
defined parameter will be sent to the remote microscope as a setting
for that device, eg:


.. code:: ini

  isWaterCooled: True
  targetTemperature: -80

Will set the remote parameters as specified, this example is from an
Andor iXon EMCCD device and will enable the watercooling switch and
set the temperature to -80 C. 


Non Python-Microscope devices
`````````````````````````````

There are several legacy devices that still exist that require a range
of parameters as they were created before direct hardware control was
moved into Python-Microscope. It is hoped that these devices will be
migrated to microscope and adopt the standard config names and syntax
as defined for the existing devices, including most configuration
being done in microscope. Currently the existing legacy devices
include the Boulder/Meadowlark SLM, the Aerotech lifter, PI M678
stage controller, Stanford sr470 shutter controller.
