This directory contains code for setting up and running experiments. 

experimentConfigPanel.py: Embedded into the dialogs the two below modules 
  create; this handles setting the parameters for experiments and actually 
  invoking them.
multiSiteExperiment.py: Handles parameters for experiments dealing with sites
  previously marked in the mosaic. Also handles the logic for going to sites
  and invoking experiments at each one.
singleSiteExperiment.py: Runs experiments at the current stage position.
