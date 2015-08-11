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
            (0, 10),
            (0, 10),
            #[1.11, 1.32, 0.96], # actual values we want
            [0, 0.22, -0.15], # values less startup_value, which the dumb DSP insists must be > 0.16
            0,
            1.11,
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
            100,
         )  
        ]
