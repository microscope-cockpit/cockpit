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
            1,          # on analogue out 2
            1,          # 1V per V
            (.5, 10),
            (0.5, 10),
            [1.91,2.13,1.75], # overloaded as pol-rotator voltages
            2,
            2.0
         ),
         (
            'z_insert',
            'z',
            0,          # on analogue out 0
            25,         # microns / V
            (0, 250),
            (0, 250),
            [.05, .1, .5, 1, 2, 5, 10],
            2,
            100,
         )  
        ]
