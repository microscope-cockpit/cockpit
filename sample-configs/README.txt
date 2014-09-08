This folder contains sample config files for various devices.
  
    my-scope.conf - a config file that defines settings required
                    to connect to equipment with fairly simple settings,
                    such as the PI M687 XY stage.

  Some device settings are difficult to describe in a simple config
  file.  For now, they are set out in python source which is parsed
  by the config module's __init__, but this may be replaced with a 
  compatible implementation in the future.

    cameras.py - a python file that defines cameras.
    lights.py  - a python file that defines light sources.
    analog.py  - a python file that defines anologue IO.
