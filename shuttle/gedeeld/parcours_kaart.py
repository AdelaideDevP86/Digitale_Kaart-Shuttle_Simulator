"""Digitale kaart. Deze module gebruikt geen ESP32-hardware of PC-pakketten.

Zie GEDEELD_API.md voor het JSON-formaat en de afspraken met de andere modules.
Een poort wijst VAN een knoop naar buiten, bijvoorbeeld N, E, S of W.
"""

import json


def _tekst(waarde):
    return isinstance(waarde, str) and bool(waarde.strip())


def _register(lijst, naam):
    """Maak een eigen register, zodat invoer later niet ongemerkt verandert."""
    if not isinstance(lijst, list):
        raise ValueError(naam + " moet een lijst zijn")
    resultaat = {}
    for item in lijst:
        if not isinstance(item, dict) or not _tekst(item.get("id")):
            raise ValueError(naam + ": elk onderdeel heeft een tekst-id nodig")
        sleutel = item["id"]
        if sleutel in resultaat:
            raise ValueError(naam + ": dubbele id " + sleutel)
        resultaat[sleutel] = dict(item)
    return resultaat


class ParcoursKaart:
    """Bewaart de aansluitingen en serviceprofielen van precies een kaartversie.

    Gebruik blokkeer/deblokkeer voor afsluitingen. Verander de registers niet
    tijdens een rit; laad voor een andere topologie een nieuwe kaartversie.
    """

    def __init__(self, gegevens):
        if not isinstance(gegevens, dict):
            raise ValueError("De kaart moet een dictionary zijn")
        self.versie = gegevens.get("versie")
        self.profiel = gegevens.get("profiel", "logisch")
        self.depot = gegevens.get("depot")
        self.start_edge = gegevens.get("start_edge")
        herkenning = gegevens.get("depot_herkenning", {})
        if not isinstance(herkenning, dict):
            raise ValueError("depot_herkenning moet een dictionary zijn")
        self.depot_herkenning = dict(herkenning)
        self.knopen = _register(gegevens.get("knopen"), "knopen")
        self.verbindingen = _register(gegevens.get("verbindingen"), "verbindingen")
        self.attracties = _register(gegevens.get("attracties"), "attracties")
        self.geblokkeerd = set()
        fouten = self.valideer()
        if fouten:
            raise ValueError("Ongeldige kaart: " + "; ".join(fouten))
        self._aansluitingen = {k: [] for k in self.knopen}
        for edge_id in sorted(self.verbindingen):
            edge = self.verbindingen[edge_id]
            self._aansluitingen[edge["a"]].append(edge_id)
            self._aansluitingen[edge["b"]].append(edge_id)

    @classmethod
    def uit_bestand(cls, pad):
        """Laad JSON. Het pad is relatief aan de map vanwaar je Python start."""
        with open(pad, "r") as bestand:
            return cls(json.load(bestand))

    def valideer(self):
        """Geef fouten als lijst terug; een geldige kaart geeft []."""
        fouten = []
        if not _tekst(self.versie):
            fouten.append("versie ontbreekt")
        if self.profiel not in ("logisch", "robot"):
            fouten.append("profiel moet logisch of robot zijn")
        if not self.knopen:
            fouten.append("geen knopen")
        gebruikte_poorten = set()
        buren = {k: [] for k in self.knopen}
        for knoop_id, knoop in self.knopen.items():
            if knoop.get("soort") not in ("depot", "keuze", "hoek", "eindpunt"):
                fouten.append(knoop_id + ": onbekende soort")
            poorten = knoop.get("poorten")
            if (not isinstance(poorten, str) or not poorten
                    or any(p not in "NESW" for p in poorten)
                    or len(set(poorten)) != len(poorten)):
                fouten.append(knoop_id + ": ongeldige poorten")
                continue
            soort = knoop.get("soort")
            aantal = 1 if soort in ("depot", "eindpunt") else 2 if soort == "hoek" else None
            if aantal is not None and len(poorten) != aantal:
                fouten.append(knoop_id + ": verkeerd aantal poorten")
            if knoop.get("soort") == "keuze" and len(poorten) < 3:
                fouten.append(knoop_id + ": keuzepunt heeft minstens drie poorten")
        for edge_id, edge in self.verbindingen.items():
            a, b = edge.get("a"), edge.get("b")
            if not isinstance(a, str) or not isinstance(b, str) or a not in buren or b not in buren:
                fouten.append(edge_id + ": onbekende eindknoop")
                continue
            if a == b:
                fouten.append(edge_id + ": verbinding naar dezelfde knoop")
                continue
            if type(edge.get("actief", True)) is not bool:
                fouten.append(edge_id + ": actief moet True of False zijn")
            buren[a].append(b)
            buren[b].append(a)
            for knoop_id, veld in ((a, "a_poort"), (b, "b_poort")):
                poort = edge.get(veld)
                poorten = self.knopen[knoop_id].get("poorten", "")
                if (not isinstance(poort, str) or len(poort) != 1
                        or poort not in "NESW" or not isinstance(poorten, str)
                        or poort not in poorten):
                    fouten.append(edge_id + ": ongeldige " + veld)
                    continue
                paar = (knoop_id, poort)
                if paar in gebruikte_poorten:
                    fouten.append(knoop_id + ": poort " + poort + " is dubbel gebruikt")
                gebruikte_poorten.add(paar)
        for knoop_id, knoop in self.knopen.items():
            poorten = knoop.get("poorten")
            if isinstance(poorten, str):
                for poort in poorten:
                    if (knoop_id, poort) not in gebruikte_poorten:
                        fouten.append(knoop_id + ": poort " + poort + " is niet verbonden")
        if not isinstance(self.depot, str) or self.depot not in self.knopen:
            fouten.append("depot verwijst niet naar een knoop")
        elif self.knopen[self.depot].get("soort") != "depot":
            fouten.append("depotknoop heeft niet soort depot")
        elif sum(k.get("soort") == "depot" for k in self.knopen.values()) != 1:
            fouten.append("de kaart moet precies een depot bevatten")
        else:
            gezien, wachtrij = {self.depot}, [self.depot]
            for knoop_id in wachtrij:
                for naast in buren[knoop_id]:
                    if naast not in gezien:
                        gezien.add(naast)
                        wachtrij.append(naast)
            if len(gezien) != len(self.knopen):
                fouten.append("niet alle knopen zijn met het depot verbonden")
        if (not isinstance(self.start_edge, str) or self.start_edge not in self.verbindingen
                or self.depot not in (self.verbindingen[self.start_edge].get("a"),
                                      self.verbindingen[self.start_edge].get("b"))):
            fouten.append("start_edge moet op het depot aansluiten")
        serviceknopen = set()
        for doel_id, doel in self.attracties.items():
            knoop = doel.get("doelknoop")
            if not isinstance(knoop, str) or knoop not in self.knopen or knoop == self.depot:
                fouten.append(doel_id + ": ongeldige doelknoop")
                continue
            if knoop in serviceknopen:
                fouten.append(doel_id + ": serviceknoop is al aan een attractie gekoppeld")
            serviceknopen.add(knoop)
            for veld in ("aankomst_edge", "vertrek_edge"):
                eid = doel.get(veld)
                if (not isinstance(eid, str) or eid not in self.verbindingen
                        or knoop not in (self.verbindingen[eid].get("a"),
                                         self.verbindingen[eid].get("b"))):
                    fouten.append(doel_id + ": ongeldige " + veld)
            if type(doel.get("gevalideerd", False)) is not bool:
                fouten.append(doel_id + ": gevalideerd moet True of False zijn")
        return fouten

    def actief(self, edge_id):
        edge = self.verbindingen[edge_id]
        return edge.get("actief", True) and edge_id not in self.geblokkeerd

    def blokkeer(self, edge_id):
        if edge_id not in self.verbindingen:
            raise ValueError("Onbekende verbinding: " + str(edge_id))
        self.geblokkeerd.add(edge_id)

    def deblokkeer(self, edge_id):
        if edge_id not in self.verbindingen:
            raise ValueError("Onbekende verbinding: " + str(edge_id))
        self.geblokkeerd.discard(edge_id)

    def andere_kant(self, knoop_id, edge_id):
        if edge_id not in self.verbindingen:
            raise ValueError("Onbekende verbinding: " + str(edge_id))
        edge = self.verbindingen[edge_id]
        if knoop_id == edge["a"]:
            return edge["b"]
        if knoop_id == edge["b"]:
            return edge["a"]
        raise ValueError(edge_id + " sluit niet aan op " + str(knoop_id))

    def poort(self, knoop_id, edge_id):
        self.andere_kant(knoop_id, edge_id)  # Controleer de aansluiting.
        edge = self.verbindingen[edge_id]
        return edge["a_poort"] if knoop_id == edge["a"] else edge["b_poort"]

    def buren(self, knoop_id):
        if knoop_id not in self.knopen:
            raise ValueError("Onbekende knoop: " + str(knoop_id))
        return [(self.andere_kant(knoop_id, eid), eid)
                for eid in self._aansluitingen[knoop_id] if self.actief(eid)]

    def beweging(self, knoop_id, in_edge, uit_edge):
        """Bereken de richting. Of keren is toegestaan controleert de planner."""
        uit_poort = self.poort(knoop_id, uit_edge)
        if in_edge is None:
            if knoop_id != self.depot or uit_edge != self.start_edge:
                raise ValueError("Zonder aankomstrichting mag je alleen vanuit het depot starten")
            return "vertrek"
        in_poort = self.poort(knoop_id, in_edge)
        verschil = ("NESW".index(uit_poort) - "NESW".index(in_poort)) % 4
        return ("keren", "links", "rechtdoor", "rechts")[verschil]

    def doelknoop(self, attractie_id):
        return self.serviceprofiel(attractie_id)["doelknoop"]

    def serviceprofiel(self, attractie_id):
        if not isinstance(attractie_id, str) or attractie_id not in self.attracties:
            raise ValueError("Onbekende attractie: " + str(attractie_id))
        return dict(self.attracties[attractie_id])

    def controleer_robotprofiel(self, bestemmingen):
        """Een ongeteste logische kaart mag niet per ongeluk robotplan worden."""
        if self.profiel != "robot":
            raise ValueError("Dit is een logische kaart, geen gevalideerd robotprofiel")
        if (self.depot_herkenning.get("gevalideerd") is not True
                or not _tekst(self.depot_herkenning.get("methode"))):
            raise ValueError("Depot-/startmethode is niet gevalideerd")
        for doel_id in bestemmingen:
            profiel = self.serviceprofiel(doel_id)
            if profiel.get("gevalideerd") is not True or not _tekst(profiel.get("herkenning")):
                raise ValueError("Serviceprofiel niet gevalideerd: " + doel_id)
