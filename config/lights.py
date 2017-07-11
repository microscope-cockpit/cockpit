ipAddress = '192.168.1.2'
light_keys = ['label','wavelength', 'color', 'triggerLine','simtheta','port','device']
WAVELENGTH_TO_COLOR = {
    405: (180, 30, 230),
    488: (40, 130, 180),
    561: (176, 255, 0),
    640: (255, 40, 40),
    'white': (255, 255, 255)
}

lights = [
 #   ('405nm', 405, WAVELENGTH_TO_COLOR[405], 1<<1, 10, 7776, 'deepstar405'),
    ('488nm', 488, WAVELENGTH_TO_COLOR[488], 1<<0, 9, 7776, 'deepstar488'),
    ('561nm', 561, WAVELENGTH_TO_COLOR[561], 1<<3, 8, 7776, 'cobolt561'),
    ('647nm', 640, WAVELENGTH_TO_COLOR[640], 1<<2, 8, 7776, 'deepstar647'),
    ('Trans', 'Trans', WAVELENGTH_TO_COLOR['white'], 1<<4), ]

