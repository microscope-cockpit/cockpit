This directory contains all of the UI code for the system. All of the 
widgets that are not created by specific devices live here -- the mosaic, 
macro stage view, camera window, etc. Several UI computers automatically 
adjust themselves based on the number and capabilities of the hardware 
available.

 * camera: all code related to the camera views window.
 * dialogs: contains all dialog subclasses and any widgets that are specific
   to them. This includes the experiment setup dialogs.
 * imageViewer: generic code for displaying pixel arrays to the screen. 
 * macroStage: all code related to the macro stage view and experiment 
   histogram.
 * mosaic: all code related to the mosaic viewer.

Other modules:

adminWindow.py: Handles some basic administrative tasks, including setting the 
  default window positions for new users, and creating new user directories. 
  This window must be created from the commandline:
  import gui.adminWindow; gui.adminWindow.makeWindow()
  
fileViewerWindow.py: Displays MRC files; this code is invoked when an MRC file
  is dragged onto the main window. 
  
guiUtils.py: Utility functions for setting up and running the UI.

keyboard.py: Binds keyboard shortcuts to windows.

loggingWindow.py: Displays standard output and standard error.

mainWindow.py: Shows exposure settings, the run-experiment buttons, and any 
  custom UI created by device code.
  
saveTopBottomPanel.py: A panel used by the macro stage viewer code. 

shellWindow.py: Sets up a Python shell (the command line). 

statusLightsWindow.py: Displays status information (e.g. images received 
  during experiments). 
  
toggleButton.py: Utility module for the ToggleButton class used throughout the 
  UI.
