"""Een ruwe passage is nog geen bewijs van welk kaartpunt dit is."""
from .config import verschil_ms
from .lijnvolger import geldig, gewone_lijn


class KruispuntDetector:
    def __init__(self, instellingen=None):
        self.instellingen = dict(instellingen or {"breed_ms": 10, "vrij_ms": 25})
        self.reset()

    def reset(self):
        self.vrijgegeven = False
        self.kandidaat_sinds_ms = None
        self.lijn_sinds_ms = None
        self.passage_seq = 0
        self._links = self._rechts = False
        self._links_sinds = self._rechts_sinds = None

    def bevestig_verlaten(self):
        # Alleen aanroepen NA een al bevestigde gewone uitgaande lijn.
        self.vrijgegeven = True
        self.kandidaat_sinds_ms = self.lijn_sinds_ms = None
        self._links = self._rechts = False
        self._links_sinds = self._rechts_sinds = None

    def update(self, nu_ms, patroon):
        if not geldig(patroon):
            raise ValueError("Verwacht vijf genormaliseerde lijnsensorbits")
        if gewone_lijn(patroon):
            self.kandidaat_sinds_ms = None
            self._links = self._rechts = False
            self._links_sinds = self._rechts_sinds = None
            if self.lijn_sinds_ms is None:
                self.lijn_sinds_ms = nu_ms
            if verschil_ms(nu_ms, self.lijn_sinds_ms) >= self.instellingen["vrij_ms"]:
                self.vrijgegeven = True
            return None
        self.lijn_sinds_ms = None
        breed = ((patroon[0] == "1" and "1" in patroon[1:3]) or
                 (patroon[4] == "1" and "1" in patroon[2:4]))
        if not breed or not self.vrijgegeven:
            self.kandidaat_sinds_ms = None
            self._links = self._rechts = False
            self._links_sinds = self._rechts_sinds = None
            return None
        if self.kandidaat_sinds_ms is None:
            self.kandidaat_sinds_ms = nu_ms
        # Een losse buitenste sensorflits is nog geen bevestigde zijtak.
        for kant, index in (("links", 0), ("rechts", 4)):
            veld = "_" + kant + "_sinds"
            sinds = getattr(self, veld)
            if patroon[index] != "1":
                setattr(self, veld, None)
            else:
                if sinds is None:
                    sinds = nu_ms
                    setattr(self, veld, sinds)
                if verschil_ms(nu_ms, sinds) >= self.instellingen.get("zijden_ms", 10):
                    setattr(self, "_" + kant, True)
        if verschil_ms(nu_ms, self.kandidaat_sinds_ms) < self.instellingen["breed_ms"]:
            return None
        self.passage_seq += 1
        self.vrijgegeven = False
        return {"soort": "punt", "passage_seq": self.passage_seq,
                "links": self._links, "rechts": self._rechts,
                "midden": patroon[2] == "1", "patroon": patroon}
