## Maps dye names to colors to use for those dyes.
DYE_TO_COLOR = {
        'Cy5': (0, 255, 255),
        'DAPI': (184, 0, 184),
        'DIC': (128, 128, 128),
        'FITC': (80,255,150),
        'GFP': (0, 255, 0),
        'mCherry': (255, 0, 0),
        'RFP': (255, 0, 0),
        'Rhod': (255,80,20),
        'YFP': (255, 255, 0),
        'TRITC': (255,165,0),
        'ND': (200, 200, 200)
}


## Return a colour tuple for a given dye.
def dyeToColor(dye, wavelength=None):
    if dye in DYE_TO_COLOR.keys():
        return DYE_TO_COLOR[dye]
    elif wavelength:
        return wavelengthToColor(wavelength)
    else:
        return DYE_TO_COLOR['ND']


## Given a wavelength in nm, return an RGB color tuple. 
def wavelengthToColor(wavelength, saturation=1):
    wavelength = float(wavelength)
    # Convert wavelength to hue, with a color wheel that ranges from
    # blue (240 degrees) at 400nm to red (360 degrees) at 650nm by way of
    # green.
    hue = max(0, min(300, (650 - wavelength)))
    # Make value decrease as we leave the visible spectrum.
    decay = max(0, max(400 - wavelength, wavelength - 650))
    # Don't let value decay too much.
    value = max(.5, 1 - decay / 200.0)
    r, g, b = hsvToRgb(hue, saturation, value)
    return tuple(int(val * 255) for val in (r, g, b))


## Convert to RGB. Taken from Pyrel:
# https://bitbucket.org/derakon/pyrel/src/7c30ed65e11b5f483737df615fcc607ab6c47d8b/gui/colors.py?at=master
# In turn, adapted from http://www.cs.rit.edu/~ncs/color/t_convert.html
def hsvToRgb(hue, saturation, value):
    if saturation == 0:
        # Greyscale.
        return (value, value, value)

    hue = hue % 360
    hue /= 60.0
    sector = int(hue)
    hueDecimal = hue - sector # Portion of hue after decimal point
    p = value * (1 - saturation)
    q = value * (1 - saturation * hueDecimal)
    t = (1 - saturation * (1 - hueDecimal))

    if sector == 0:
        return (value, t, p)
    if sector == 1:
        return (q, value, p)
    if sector == 2:
        return (p, value, t)
    if sector == 3:
        return (p, q, value)
    if sector == 4:
        return (t, p, value)
    return (value, p, q)
