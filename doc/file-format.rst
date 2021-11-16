.. Copyright (C) 2021 Ian Dobbie <ian.dobbie@gmail.com>

   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".

File Format
###########

.. _Base_file_format:

Base file format
****************

Currently Cockpoit only supports the '.dv' file format which is an
extension of the mrc file format. The mrc file format is defined in
detail in `MRC/CCP4 2014 file format specification
<https://www.ccpem.ac.uk/mrc_format/mrc2014.php>`__. The CCP4
consortium of the EM community are continuing to support and extend this
file format. This support includes file validators and a detailed
specification, which is compatible with the files used here but not
identical.

Cockpit utilises the exended header to store specific optical
microscopy meta-data. In particular
both the excitation and emission wavelengths must be set to correctly
select the SIM fitting bootstrap parameters including stripe width and
k0 angles.


.. _DV_file_header:

DV file header specification
****************************


 The extended header has the following structure per
 plane (see `cockpit github issue  #290 <https://github.com/MicronOxford/cockpit/issues/290>`__)

   *  8 32bit signed integers, often are all set to zero.
   *  Followed by 32 32bit floats.  We only what the first 14 are:


.. list-table:: DV extended header values 
   :widths: 25 75 
   :header-rows: 1 
 
   * - Float index
     - Meta data content
   * - 0
     - photosensor reading (typically in mV)
   * - 1
     - elapsed time (seconds since experiment began)
   * - 2
     -      x stage coordinates
   * - 3
     -      y stage coordinates
   * - 4
     -      z stage coordinates
   * - 5
     -      minimum intensity
   * - 6
     -      maximum intensity
   * - 7
     -     mean intensity
   * - 8
     -      exposure time (seconds)
   * - 9
     -      neutral density (fraction of 1 or percentage)
   * - 10
     -      excitation wavelength
   * - 11
     -      emission wavelength
   * - 12
     -      intensity scaling (usually 1)
   * - 13
     -      energy conversion factor (usually 1)
   
   	  
Software supporting .dv files.
*****************************

Although a realtively uncommon format, the .dv file format is supprted
by the bioformats project allowing import of .dv files into software
using this library including imageJ, OMERO and matlab. Additionally,
the `Chromagnon <https://github.com/macronucleus/Chromagnon>`__ image
alignment tool will read and write .dv files and it is the native
format for DeltaVision microscopes utilising the commerical package
SoftWoRx.
