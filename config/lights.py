ipAddress = '172.16.0.21'
light_keys = ['label','wavelength', 'color', 'triggerLine','simtheta','port','device']
WAVELENGTH_TO_COLOR = {
    405: (180, 30, 230),
    488: (40, 130, 180),
    561: (176, 255, 0),
    640: (255, 40, 40),
    'white': (255, 255, 255)
}

lights = [
#    ('ambient', 'Ambient', WAVELENGTH_TO_COLOR['white'], 1<<5),
#    ('405nm', 405, WAVELENGTH_TO_COLOR[405], 1<<13, 10),
#    ('488nm', 488, WAVELENGTH_TO_COLOR[488], 1<<9, 9, 7776, 'deepstar'),
#    ('561nm', 561, WAVELENGTH_TO_COLOR[561], 1<<13, 8),
#    ('DIC', 'DIC', WAVELENGTH_TO_COLOR['white'], 1<<6),
    ('488nm', 520, WAVELENGTH_TO_COLOR[488], 1<<9),
]
