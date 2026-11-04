"""Gedeelde teken- en animatiegeometrie, in schematische eenheden."""
import math


def bemonster(geometrie, aantal=80):
    punten = geometrie['points']
    if geometrie['kind'] == 'polyline':
        return [tuple(p) for p in punten]
    if geometrie['kind'] != 'cubic_bezier' or len(punten) != 4:
        raise ValueError('Onbekende tekengeometrie')
    resultaat = []
    for i in range(aantal + 1):
        t = i / aantal
        gewichten = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
        resultaat.append(tuple(sum(w*p[as_] for w,p in zip(gewichten,punten)) for as_ in (0,1)))
    return resultaat


def lengte(punten):
    return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(punten,punten[1:]))


def op_pad(punten, fractie):
    """Constante afstand langs de lijn, met hoek in schermcoordinaten."""
    resterend = max(0,min(1,fractie)) * lengte(punten)
    for i,(a,b) in enumerate(zip(punten,punten[1:])):
        afstand = math.hypot(b[0]-a[0],b[1]-a[1])
        if resterend <= afstand or i == len(punten)-2:
            t = min(1,resterend/afstand) if afstand else 0
            return (a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),
                    math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])))
        resterend -= afstand
    return punten[0][0],punten[0][1],0
