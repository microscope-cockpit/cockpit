ipAddress = 'dsp.b24'
light_keys = ['label','wavelength', 'color', 'triggerLine','simtheta','port','device']
WAVELENGTH_TO_COLOR = {
    405: (180, 30, 230),
    488: (40, 130, 180),
    561: (176, 255, 0),
    640: (255, 40, 40),
    'white': (255, 255, 255)
}

lights = [
    ('ambient', 'Ambient', WAVELENGTH_TO_COLOR['white'], 0),
    ('405nm', 405, WAVELENGTH_TO_COLOR[405], 1<<12, 10.5, 8001, 'deepstar405'),
    ('488nm', 488, WAVELENGTH_TO_COLOR[488], 1<<13, 10, 8001, 'deepstar488'),
    ('561nm', 561, WAVELENGTH_TO_COLOR[561], 1<<14, 9.5, 8001, 'cobolt561'),
    ('647nm', 647, WAVELENGTH_TO_COLOR[640], 1<<15, 9, 8001, 'deepstar647'),]
