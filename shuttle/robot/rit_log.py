"""Begrensde RAM-log; flash wordt alleen na stoppen beschreven."""
import json
from .config import verschil_ms


class RitLog:
    def __init__(self, instellingen):
        self.instellingen = dict(instellingen)
        self.events, self.metingen = [], []
        self._vorige_meting = None
        self._geschreven = None
        self._seq = 0

    def _bewaar(self, lijst, maximum, nu, soort, gegevens):
        self._seq += 1
        lijst.append(dict(seq=self._seq, ms=nu, soort=soort, **gegevens))
        if len(lijst) > maximum:
            lijst.pop(0)

    def event(self, nu, soort, gegevens=None):
        self._bewaar(self.events, self.instellingen["events_max"], nu, soort,
                     dict(gegevens or {}))

    def meet(self, nu, meting, besturing):
        if (self._vorige_meting is not None and
                verschil_ms(nu, self._vorige_meting) < self.instellingen["meet_interval_ms"]):
            return
        self._vorige_meting = nu
        self._bewaar(self.metingen, self.instellingen["metingen_max"], nu, "meting",
                     dict(patroon=meting.get("patroon"), motoren=besturing.motoren,
                          toestand=besturing.toestand, fase=besturing._fase,
                          stap=besturing.stapindex, verwacht=besturing._verwacht,
                          obstakel=bool(meting.get("obstakel"))))

    def schrijf(self, besturing=None):
        if besturing is not None and besturing.motoren != (0, 0):
            raise ValueError("Log alleen schrijven met stilstaande motoren")
        if self._geschreven == self._seq:
            return False
        regels = sorted(self.events + self.metingen, key=lambda r: r["seq"])
        with open(self.instellingen["pad"], "w") as bestand:
            for regel in regels:
                bestand.write(json.dumps(regel) + "\n")
        self._geschreven = self._seq
        return True
