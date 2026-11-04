"""Afstandsregeling met hysterese. Momenteel staat de niet-aangesloten sensor uit.

Een toekomstige meter moet snel een afstand in millimeters of None teruggeven.
Deze module verzint geen trigger-/echo-pinnen en importeert geen sensordriver.
"""
from .config import verschil_ms


class ObjectDetectie:
    def __init__(self, instellingen, meter=None):
        self.instellingen = dict(instellingen)
        self.meter = meter
        self.geblokkeerd = bool(instellingen["aan"])
        self.laatste_ms = None
        self.geldig_ms = None
        self.afstand_mm = None
        if instellingen["stop_mm"] >= instellingen["vrij_mm"]:
            raise ValueError("vrij_mm moet groter zijn dan stop_mm")

    def update(self, nu_ms, afstand_mm=None):
        c = self.instellingen
        if not c["aan"]:
            self.geblokkeerd = False
            return False
        if self.laatste_ms is None or verschil_ms(nu_ms, self.laatste_ms) >= c["meet_interval_ms"]:
            self.laatste_ms = nu_ms
            if afstand_mm is None and self.meter is not None:
                afstand_mm = self.meter()
            if isinstance(afstand_mm, (int, float)) and 0 < afstand_mm < float("inf"):
                self.afstand_mm, self.geldig_ms = afstand_mm, nu_ms
                if afstand_mm <= c["stop_mm"]:
                    self.geblokkeerd = True
                elif afstand_mm >= c["vrij_mm"]:
                    self.geblokkeerd = False
        if self.geldig_ms is None or verschil_ms(nu_ms, self.geldig_ms) > c["max_leeftijd_ms"]:
            self.geblokkeerd = True
        return self.geblokkeerd
