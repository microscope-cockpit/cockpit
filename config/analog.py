aout_keys = ['name', 
             'cockpit_axis', 
             'aline', 
             'sensitivity', 
             'hard_limits', 
             'soft_limits', 
             'deltas', 
             'default_delta',
             'startup_value',]

aouts = [(
           'polrot',   # polarisation rotatoar
           'SI angle',    # moves angle 
           2,          # on analogue out 2
           1,          # 1V per V
           (0, 10),
           (None, None),
           [0.01, 0.05, 0.1, 0.5, 1],
           2,
           None
           ),
         (
           'z_insert',
           'z',
           0,          # on analogue out 0
           20,         # microns / V
           (0, 100),
           (0, 91.13),
           [.05, .1, .5, 1, 2, 5, 10],
           2,
           45,
          )  
        ]
