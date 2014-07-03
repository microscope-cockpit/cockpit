## _lights [(label, wavelength, dsp line, sim diffraction angle at slm),...]
light_keys = ['label','wavelength','line','simtheta']
lights = [
    ('ambient', 'Ambient', 0),
    ('405nm', 405, 1<<13, 10),
    ('488nm', 488, 1<<9, 9),
    ('560nm', 560, 1<<13, 8),
    ('DIC', 'DIC', 1<<11),]
