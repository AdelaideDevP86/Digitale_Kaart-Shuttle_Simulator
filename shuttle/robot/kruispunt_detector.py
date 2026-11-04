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

    def bevestig_verlaten(self):
        # Alleen aanroepen NA een al bevestigde gewone uitgaande lijn.
        self.vrijgegeven = True
        self.kandidaat_sinds_ms = self.lijn_sinds_ms = None
        self._links = self._rechts = False

    def update(self, nu_ms, patroon):
        if not geldig(patroon):
            raise ValueError("Verwacht vijf genormaliseerde lijnsensorbits")
        if gewone_lijn(patroon):
            self.kandidaat_sinds_ms = None
            self._links = self._rechts = False
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
            return None
        if self.kandidaat_sinds_ms is None:
            self.kandidaat_sinds_ms = nu_ms
        self._links = self._links or patroon[0] == "1"
        self._rechts = self._rechts or patroon[4] == "1"
        if verschil_ms(nu_ms, self.kandidaat_sinds_ms) < self.instellingen["breed_ms"]:
            return None
        self.passage_seq += 1
        self.vrijgegeven = False
        return {"soort": "punt", "passage_seq": self.passage_seq,
                "links": self._links, "rechts": self._rechts,
                "midden": patroon[2] == "1", "patroon": patroon}
