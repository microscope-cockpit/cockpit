This directory contains all the code needed to run experiments. Setup of 
experiments is done in the gui/dialogs/experiment directory, but that code 
ultimately just creates an Experiment subclass (e.g. ZStackExperiment) with
appropriate parameters.

Each Experiment subclass is responsible for registering itself in 
experimentRegistry.py so that the gui/dialogs/experiment modules know what
experiments are available.

actionTable.py: Describe the sequence of actions that take place as part of 
  the experiment. 

dataSaver.py: Handles incoming image data, saving it to disk as it comes in.

experiment.py: Base Experiment class that all other experiments subclass from. 
  Never used directly on its own. The experiment.lastExperiment value holds
  the last class instance that was used to run an experiment, which can be 
  useful for debugging.
  
offsetGainCorrection.py: Generates offset/gain correction files (which add
  an offset to pixel values and then multiply them by a gain factor). 

responseMap.py: Generates response map correction files (which use detailed
  response maps of the cameras, combined with linear interpolation, to correct
  for nonlinear camera response).
  
structuredIllumination.py: Runs SI experiments.

sweptShutter.py: Does an open-shutter sweep in Z.

zStack.py: Standard Z-stack experiment. 

zStackMulti.py: Unofficial module for running Z-stacks with multiple different
  exposure times depending on the (hardcoded) criterion.
