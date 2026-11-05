"""Niet-blokkerende uitvoering van de gedeelde RoutePlanner-stappen.

Een rijstap is de UITGANG van de van-knoop. Na bevestigd verlaten rijdt de
robot over via naar naar. Pas een volgende passage bevestigt de aankomst.
"""
from . import config, lijnvolger


class RitBesturing:
    def __init__(self, planner, detector, mqtt, rijd, instellingen=None, voor_robot=True, log=None):
        self.planner, self.detector, self.mqtt = planner, detector, mqtt
        self._rijd = rijd
        self.instellingen = dict(instellingen or config.RIJDEN)
        self.voor_robot = voor_robot
        self.log = log
        if voor_robot != (mqtt.bron == "robot"):
            raise ValueError("Robotbesturing en MQTT moeten dezelfde bron gebruiken")
        self.toestand, self.hervat_toestand = "GEREED", None
        self.positie = {"laatste_punt": None, "in_edge": None,
                        "op_knoop": False, "status": "onzeker"}
        self.plan = None
        self.stapindex = 0
        self.bezoeken, self.alle_doelen = [], []
        self.opdracht, self.wachtend = None, None
        self.laatste_passage_seq = self.status_seq = 0
        self.laatste_resultaat = None
        self.motoren = (0, 0)
        self.reden = "Startpositie nog niet bevestigd"
        self._pid = lijnvolger.nieuwe_pid()
        self._real_ms = None
        self._actief_ms = 0
        self._service_sinds = None
        self._huidige_edge = self._verwacht = None
        self._beweging = self._fase = None
        self._stabiel = self._zoek_sinds = None
        self._marker = None
        self._punt = self._eind_sinds = None
        self._fout = False
        self._laatste_status = None
        self._vorige_status_ms = 0

    def _trace(self, soort, **gegevens):
        if self.log is not None:
            gegevens.update(stap=self.stapindex, verwacht=self._verwacht, fase=self._fase)
            self.log.event(self._real_ms, soort, gegevens)

    def _motor(self, links=0, rechts=0):
        self.motoren = (links, rechts)
        self._rijd(links, rechts)

    def bevestig_start(self):
        """Handmatig, alleen wanneer de robot echt in het depot klaarstaat."""
        if self.toestand not in ("GEREED", "GESTOPT", "KLAAR"):
            raise ValueError("Eerst stoppen voor opnieuw bevestigen")
        self._motor()
        self.positie = {"laatste_punt": self.planner.kaart.depot, "in_edge": None,
                        "op_knoop": True, "status": "start_bevestigd"}
        self.plan = None
        self.toestand, self.reden = "GEREED", ""
        self._fout = False
        self._huidige_edge = self._verwacht = None

    def _afwijzen(self, opdracht, reden):
        self.mqtt.bevestig(opdracht.get("command_id"), "rejected", reden)
        return {"resultaat": "rejected", "reden": reden}

    def ontvang(self, opdracht):
        if not self.mqtt.controleer_opdracht(opdracht):
            return {"resultaat": "gefilterd"}
        actie = opdracht["actie"]
        if actie == "stop":
            self._stop("Expliciete stopopdracht", fout=False)
            self.wachtend = None
            self.mqtt.bevestig(opdracht["command_id"], "accepted", "gestopt")
            return {"resultaat": "accepted"}
        try:
            if opdracht.get("kaartversie") != self.planner.kaart.versie:
                raise ValueError("Kaartversie verschilt")
            doelen = self.planner._bestemmingen_controleren(opdracht.get("bestemmingen"))
            if not isinstance(opdracht.get("mission_id"), str) or not opdracht["mission_id"].strip():
                raise ValueError("mission_id ontbreekt")
            if type(opdracht.get("revisie")) is not int or opdracht["revisie"] < 1:
                raise ValueError("Ongeldige revisie")
            if actie == "start":
                if self.toestand not in ("GEREED", "KLAAR"):
                    raise ValueError("Er loopt al een rit of de robot is gestopt")
                plan = self.planner.plan(self.positie, doelen, voor_robot=self.voor_robot)
                self._controleer_herkenning(doelen)
                self._controleer_installatie(plan)
                self.bezoeken = []
                self.alle_doelen = list(doelen)
                self.wachtend = None
                self.detector.reset()
                self.laatste_passage_seq = 0
                self._pid = lijnvolger.nieuwe_pid()
                self._installeer(plan, opdracht)
                self.mqtt.bevestig(opdracht["command_id"], "accepted")
            elif actie == "vervang":
                if self.opdracht is None or self.toestand in ("GEREED", "KLAAR", "GESTOPT"):
                    raise ValueError("Geen actieve rit om te wijzigen")
                if opdracht["mission_id"] != self.opdracht["mission_id"]:
                    raise ValueError("Wijziging hoort bij andere rit")
                hoogste = max(self.opdracht["revisie"], self.wachtend["revisie"] if self.wachtend else 0)
                if opdracht["revisie"] <= hoogste:
                    raise ValueError("Revisie is niet nieuwer")
                if any(d in self.bezoeken for d in doelen):
                    raise ValueError("Al bezochte attractie opnieuw gevraagd")
                if self.voor_robot:
                    self.planner.kaart.controleer_robotprofiel(doelen)
                self._controleer_herkenning(doelen)
                self.wachtend = dict(opdracht)
                self.mqtt.bevestig(opdracht["command_id"], "pending")
            else:
                raise ValueError("Onbekende actie")
        except ValueError as fout:
            return self._afwijzen(opdracht, str(fout))
        return {"resultaat": "accepted" if actie == "start" else "pending"}

    def _controleer_herkenning(self, doelen):
        if not self.voor_robot:
            return
        methoden = ("anker", "rechtertak", "linkertak", "t_splitsing", "zwart_blok", "lijneinde")
        for doel in doelen:
            if self.planner.kaart.serviceprofiel(doel).get("herkenning") not in methoden:
                raise ValueError("Onbekende halteherkenning bij " + doel)
            if (self.planner.kaart.serviceprofiel(doel).get("herkenning") == "lijneinde"
                    and self.planner.kaart.knopen[self.planner.kaart.doelknoop(doel)]["soort"] != "eindpunt"):
                raise ValueError("Lijneindeherkenning vereist een eindpunt bij " + doel)
        if self.planner.kaart.depot_herkenning.get("methode") not in ("anker", "t_splitsing", "zwart_blok"):
            raise ValueError("Onbekende depotmethode")

    def _controleer_installatie(self, plan):
        fouten = self.planner.valideer_plan(plan)
        if fouten:
            raise ValueError("; ".join(fouten))
        if self.voor_robot:
            # De planner mag een eindpunt ook als tussenliggende keerplaats
            # gebruiken. Ook zo'n ONGEVRAAGD eindpunt moet herkenbaar zijn.
            for stap in plan["stappen"]:
                doel = stap.get("naar")
                if doel and self.planner.kaart.knopen[doel]["soort"] in ("eindpunt", "depot"):
                    methode = self._herkenning_voor(doel)
                    if methode not in ("anker", "rechtertak", "linkertak", "t_splitsing", "zwart_blok", "lijneinde"):
                        raise ValueError("Geen gevalideerde herkenning voor eindpunt " + doel)

    def _installeer(self, plan, opdracht):
        self._controleer_installatie(plan)
        self.plan, self.opdracht = plan, dict(opdracht)
        self.stapindex = 0
        self._huidige_edge = self._verwacht = self._marker = None
        self._punt = self._eind_sinds = None
        self._fout = False
        self._service_sinds = self._stabiel = self._zoek_sinds = None
        self._beweging = self._fase = None
        self.toestand, self.reden = "RIJDEN", ""

    def pas_wachtende_opdracht_toe(self):
        if self.wachtend is None or not self.positie["op_knoop"] or self.positie["status"] == "onzeker":
            return False
        nieuw = self.wachtend
        if any(d in self.bezoeken for d in nieuw["bestemmingen"]):
            self.mqtt.bevestig(nieuw["command_id"], "rejected", "Doel is intussen bediend")
            self.wachtend = None
            return False
        try:
            plan = self.planner.plan(self.positie, nieuw["bestemmingen"], voor_robot=self.voor_robot)
            self._controleer_installatie(plan)
        except ValueError as fout:
            self.mqtt.bevestig(nieuw["command_id"], "rejected", str(fout))
            self.wachtend = None
            return False
        self.alle_doelen = list(self.bezoeken) + list(nieuw["bestemmingen"])
        self._installeer(plan, nieuw)
        self.wachtend = None
        self.mqtt.bevestig(nieuw["command_id"], "applied")
        return True

    def _stop(self, reden, onzeker=True, fout=True):
        self._motor()
        self.toestand, self.reden = "GESTOPT", reden
        self._fout = fout
        if fout:
            self.laatste_resultaat = {"mission_id": self.opdracht["mission_id"] if self.opdracht else None,
                                     "resultaat": "fout", "reden": reden,
                                     "bezocht": list(self.bezoeken)}
        self._trace("stop", reden=reden, fout=fout)
        if onzeker:
            self.positie["status"] = "onzeker"
            self.positie["op_knoop"] = False

    def _zoeken(self, reden="Lijn kwijt", onzeker=False):
        if self.toestand != "ZOEKEN":
            self._zoek_sinds = self._actief_ms
            self._fase_voor_zoeken = self._fase
            self._trace("zoeken", reden=reden, onzeker=onzeker)
        self.toestand, self.reden = "ZOEKEN", reden
        self._stabiel = None
        if onzeker:
            self.positie["status"] = "onzeker"
        self._motor(*lijnvolger.draaicommando(self._pid["richting"], self.instellingen["zoeken"]))

    def _kies_stap(self, patroon):
        stap = self.plan["stappen"][self.stapindex]
        if stap["soort"] != "service":
            if self.pas_wachtende_opdracht_toe():
                stap = self.plan["stappen"][self.stapindex]
        if stap["soort"] == "service":
            self.toestand = "WACHTEN"
            self._service_sinds = self._actief_ms
            self._motor()
        elif stap["soort"] == "einde":
            if (self.positie["laatste_punt"] != self.planner.kaart.depot
                    or self.positie["status"] != "depot_bevestigd"
                    or self.bezoeken != self.alle_doelen):
                self._stop("Depot of bezoeken niet bevestigd")
                return
            self.toestand, self.reden = "KLAAR", ""
            self._motor()
            self.laatste_resultaat = {"mission_id": self.opdracht["mission_id"],
                                     "revisie": self.opdracht["revisie"], "resultaat": "succesvol",
                                     "bezocht": list(self.bezoeken)}
        else:
            if stap["van"] != self.positie["laatste_punt"]:
                self._stop("Rijstap begint op een ander punt")
                return
            self._beweging = stap
            self._start_beweging = self._draai_start = self._actief_ms
            self._rechtdoor_aanwezig = self._rechtdoor_bij(stap)
            self._stabiel = None
            actie = stap["actie"]
            self.toestand = "DRAAIEN" if actie in ("links", "rechts", "keren") else "RIJDEN"
            self._fase = "UITLIJNEN" if self.toestand == "DRAAIEN" else "VERLATEN"
            if actie == "keren":
                # Aan een lijneinde eerst een stukje TERUG tot de lijn weer onder de
                # sensoren ligt: dan staat het draaipunt op de lijn en vindt hij die
                # na 180 graden altijd terug. Vooruit rijden zou de baan verlaten.
                self._fase = "TERUG"
            self._trace("uitgang", van=stap["van"], naar=stap["naar"], actie=actie)
            self.positie["op_knoop"] = False
            # Na dit moment mag een routewissel niet meer dit punt gebruiken.
            self._doe_beweging(patroon)

    def _rechtdoor_bij(self, stap):
        """Ligt er op dit punt fysiek een doorgaande lijn? Ook gesloten edges tellen mee."""
        kaart, in_edge = self.planner.kaart, self.positie.get("in_edge")
        if in_edge is None:
            return False
        knoop = stap["van"]
        return any(kaart.beweging(knoop, in_edge, e) == "rechtdoor"
                   for e in kaart._aansluitingen[knoop] if e != in_edge)

    def _doe_beweging(self, p):
        stap, c = self._beweging, self.instellingen
        actie = stap["actie"]
        if self._actief_ms - self._start_beweging >= c.get("beweging_timeout_ms", 6000):
            self._stop("Uitgang niet gevonden binnen beweging_timeout_ms")
            return
        if self._fase == "TERUG":
            if p[1:4] != "000" or self._actief_ms - self._start_beweging >= c.get("terug_max_ms", 800):
                self._fase = "WIT"
                self._stabiel = None
                self._draai_start = self._actief_ms  # minimale keertijd telt vanaf het DRAAIEN
            else:
                v = c.get("halte_basis", c["basis"])
                self._motor(-v, -v)
                return
        if self._fase == "UITLIJNEN":
            if self._actief_ms - self._start_beweging < c["uitlijnen_ms"]:
                self._motor(c["basis"], c["basis"])
                return
            self._fase = "WIT"
            self._stabiel = None
        if self._fase in ("WIT", "ZWART"):
            richting = c["keer_richting"] if actie == "keren" else actie
            self._motor(*lijnvolger.draaicommando(richting, c["draaien"]))
            if self._fase == "WIT":
                if actie in ("links", "rechts") and self._rechtdoor_aanwezig:
                    # Doorgaande lijn (T of kruising): zwart dat alleen aan de draaikant
                    # ligt is nog de oude lijn; daar zou hij op terugdraaien.
                    if richting == "links":
                        draaikant, overkant = p[0:2], p[3:5]
                    else:
                        draaikant, overkant = p[3:5], p[0:2]
                    gewenst = p[2] == "0" and ("1" not in draaikant or "1" in overkant)
                else:
                    # Hoek of geen doorgaande lijn: de oude lijn ligt al achter hem,
                    # zwart aan de draaikant is de nieuwe lijn. Midden wit is genoeg.
                    gewenst = p[2] == "0"
            else:
                gewenst = p[2] == "1"
            if gewenst:
                if self._stabiel is None:
                    self._stabiel = self._actief_ms
                if self._actief_ms - self._stabiel >= c["lijn_ms"]:
                    if self._fase == "WIT":
                        self._fase = "ZWART"
                        self._stabiel = None
                    elif actie != "keren" or self._actief_ms - self._draai_start >= c["keer_min_ms"]:
                        self._fase = "VERLATEN"
                        self._stabiel = None
            else:
                self._stabiel = None
            return
        if p != "00000" and not (p[2] == "1" and (p[0] == "1" or p[4] == "1")):
            # Naast of op de lijn: bijsturen. Alleen op het kruispunt zelf blind rechtdoor.
            self._motor(*lijnvolger.volg_lijn(p, self._actief_ms, self._pid, c))
        else:
            self._motor(c["basis"], c["basis"])
        if lijnvolger.gewone_lijn(p):
            if self._stabiel is None:
                self._stabiel = self._actief_ms
            if self._actief_ms - self._stabiel >= c["lijn_ms"]:
                self._huidige_edge, self._verwacht = stap["via"], stap["naar"]
                self.positie.pop("na_service", None)
                self.positie["verwacht_punt"] = self._verwacht
                self.stapindex += 1
                self._beweging = self._fase = self._stabiel = None
                self.detector.bevestig_verlaten()
                lijnvolger.reset_pid(self._pid)
                self.toestand = "RIJDEN"
        else:
            self._stabiel = None
            if p == "00000":
                self._zoeken()

    def _aankomst(self, waarneming, p):
        if self._verwacht is None:
            return
        if waarneming.get("knoop", self._verwacht) != self._verwacht:
            self._zoeken("Waarneming past niet bij route", onzeker=True)
            return
        if waarneming.get("in_edge", self._huidige_edge) != self._huidige_edge:
            self._zoeken("Verkeerde aankomstrichting", onzeker=True)
            return
        knoop = self._verwacht
        status = "depot_bevestigd" if knoop == self.planner.kaart.depot else "route_aannemelijk"
        self.positie = {"laatste_punt": knoop, "in_edge": self._huidige_edge,
                        "op_knoop": True, "status": status}
        self._verwacht = self._huidige_edge = self._marker = None
        self._punt = self._eind_sinds = None
        self._trace("aankomst", knoop=knoop, patroon=p)
        self._kies_stap(p)

    def _doel_methode(self):
        stap = self.plan["stappen"][self.stapindex]
        if stap["soort"] == "service":
            return self.planner.kaart.serviceprofiel(stap["doel"]).get("herkenning")
        if stap["soort"] == "einde":
            return self.planner.kaart.depot_herkenning.get("methode")
        if self._verwacht and self.planner.kaart.knopen[self._verwacht]["soort"] in ("eindpunt", "depot"):
            return self._herkenning_voor(self._verwacht)
        return None

    def _herkenning_voor(self, knoop):
        if knoop == self.planner.kaart.depot:
            return self.planner.kaart.depot_herkenning.get("methode")
        for profiel in self.planner.kaart.attracties.values():
            if profiel["doelknoop"] == knoop:
                if self.voor_robot and profiel.get("gevalideerd") is not True:
                    return None
                return profiel.get("herkenning")
        return None

    def verwerk_waarneming(self, waarneming):
        """Expliciete knoopmeldingen alleen voor logische simulatie/tests."""
        if self.voor_robot:
            raise ValueError("Gebruik echte metingen via update op de robot")
        if self.toestand != "RIJDEN" or self._beweging is not None or self.positie["status"] == "onzeker":
            return
        seq = waarneming.get("passage_seq")
        if type(seq) is not int or seq <= self.laatste_passage_seq:
            return
        self.laatste_passage_seq = seq
        self._aankomst(waarneming, "11111")

    def _bevestig_punt(self, p):
        """Verzamel ontbrekende zijtakken zonder extra passage of meetstop."""
        punt, c = self._punt, self.instellingen
        for kant, index in (("links", 0), ("rechts", 4)):
            veld = kant + "_sinds"
            if p[index] == "1":
                if punt.get(veld) is None:
                    punt[veld] = self._actief_ms
                if self._actief_ms - punt[veld] >= c.get("zijden_ms", 10):
                    punt[kant] = True
            else:
                punt[veld] = None
        methode = self._doel_methode()
        if methode in ("rechtertak", "linkertak"):
            klopt = punt["rechts" if methode == "rechtertak" else "links"]
        else:
            mogelijk = [self.planner.kaart.beweging(self._verwacht, self._huidige_edge, eid)
                        for _, eid in self.planner.kaart.buren(self._verwacht)
                        if eid != self._huidige_edge]
            actie = self.plan["stappen"][self.stapindex].get("actie")
            klopt = ((punt["links"] or punt["rechts"])
                     and not (punt["links"] and "links" not in mogelijk)
                     and not (punt["rechts"] and "rechts" not in mogelijk)
                     and (actie not in ("links", "rechts") or punt[actie]))
        if klopt:
            self._trace("punt_bevestigd", patroon=p, links=punt["links"], rechts=punt["rechts"])
            self._punt = None
            self._aankomst({}, p)
        elif self._actief_ms - punt["sinds"] >= c.get("kruispunt_timeout_ms", 250):
            self._punt = None
            self._zoeken("Kruispunt blijft afwijken van geplande uitgang", onzeker=True)
        else:
            self._motor(c["basis"], c["basis"])

    def _rijden(self, nu_ms, meting):
        p, c = meting["patroon"], self.instellingen
        methode = self._doel_methode()
        if methode == "lijneinde":
            # Laatste stuk naar een halte langzamer: minder slingeren en uitrollen.
            c = dict(c, basis=c.get("halte_basis", c["basis"]))
        if methode == "anker" and meting.get("anker") == self._verwacht:
            self._aankomst({}, p)
            return
        if self._punt is not None:
            self._bevestig_punt(p)
            return
        if methode == "lijneinde":
            if p == "00000":
                if self._eind_sinds is None:
                    self._eind_sinds = self._actief_ms
                if self._actief_ms - self._eind_sinds >= c.get("lijneinde_ms", 60):
                    self._aankomst({}, p)
                else:
                    self._motor(c["basis"], c["basis"])
                return
            self._eind_sinds = None
        event = self.detector.update(nu_ms, p)
        if event and event["passage_seq"] > self.laatste_passage_seq:
            self.laatste_passage_seq = event["passage_seq"]
            self._trace("passage", patroon=p, links=event["links"], rechts=event["rechts"],
                        passage_seq=event["passage_seq"])
            if methode == "anker":
                self._zoeken("Verwacht uniek anker ontbreekt", onzeker=True)
                return
            if methode in ("zwart_blok", "t_splitsing"):
                self._marker = dict(event)
                self._marker.update(sinds=self._actief_ms, vrij=None)
            elif methode in ("rechtertak", "linkertak"):
                self._punt = dict(event, sinds=self._actief_ms)
                self._bevestig_punt(p)
                return
            elif methode == "lijneinde":
                self._zoeken("Onverwacht kruispunt op aanrit naar lijneinde", onzeker=True)
                return
            else:
                self._punt = dict(event, sinds=self._actief_ms)
                self._bevestig_punt(p)
                return
        if self._marker:
            marker = self._marker
            if self._actief_ms - marker["sinds"] >= c.get("marker_timeout_ms", 1500):
                self._marker = None
                self._zoeken("Haltemarkering niet bevestigd binnen marker_timeout_ms", onzeker=True)
                return
            marker["links"] |= p[0] == "1"
            marker["rechts"] |= p[4] == "1"
            if methode == "zwart_blok":
                if p != "11111":
                    marker["zwart_sinds"] = None
                    if p[0] == p[4] == "0":
                        self._zoeken("Breed doelvlak te kort of onderbroken", onzeker=True)
                        return
                else:
                    if marker.get("zwart_sinds") is None:
                        marker["zwart_sinds"] = self._actief_ms
                    if self._actief_ms - marker["zwart_sinds"] >= c["marker_ms"]:
                        self._aankomst({}, p)
                        return
            elif p[0] == p[4] == "0":
                if marker["vrij"] is None:
                    marker["vrij"] = self._actief_ms
                if self._actief_ms - marker["vrij"] >= c["lijn_ms"]:
                    if marker["links"] and marker["rechts"] and "1" not in p[1:4]:
                        self._aankomst({}, p)
                        return
                    self._zoeken("Verwachte T zonder doorgaande lijn ontbreekt", onzeker=True)
                    return
            else:
                marker["vrij"] = None
            # Bij het verwachte depot op het zwarte blok blijven staan tijdens
            # de bevestiging, anders kan hij het blok in marker_ms voorbijrijden.
            if methode == "zwart_blok" and p == "11111":
                self._motor()
            else:
                self._motor(c["basis"], c["basis"])
        elif p == "00000":
            self._zoeken()
        elif p[2] == "1" and (p[0] == "1" or p[4] == "1"):
            self._motor(c["basis"], c["basis"])
        else:
            self._motor(*lijnvolger.volg_lijn(p, self._actief_ms, self._pid, c))

    def update(self, nu_ms, meting):
        if not isinstance(meting, dict) or not lijnvolger.geldig(meting.get("patroon")):
            self._stop("Ongeldige sensormeting")
            self._meld_status(nu_ms)
            return
        dt = max(0, config.verschil_ms(nu_ms, self._real_ms)) if self._real_ms is not None else 0
        self._real_ms = nu_ms
        geblokkeerd = bool(meting.get("obstakel", False))
        actief = self.toestand not in ("GEREED", "GESTOPT", "KLAAR")
        if actief and geblokkeerd:
            if self.toestand != "GEBLOKKEERD":
                self.hervat_toestand = self.toestand
                self._stabiel = None
                self.detector.kandidaat_sinds_ms = self.detector.lijn_sinds_ms = None
            self.toestand = "GEBLOKKEERD"
            self._motor()
        else:
            if self.toestand == "GEBLOKKEERD":
                self.toestand, self.hervat_toestand = self.hervat_toestand, None
                lijnvolger.reset_pid(self._pid)
            else:
                self._actief_ms += dt
            p = meting["patroon"]
            if self.toestand in ("GEREED", "GESTOPT", "KLAAR"):
                self._motor()
            elif self.toestand == "WACHTEN":
                self._motor()
                stap = self.plan["stappen"][self.stapindex]
                if self._actief_ms - self._service_sinds >= stap["wacht_ms"]:
                    if stap["doel"] in self.bezoeken:
                        self._stop("Dubbele service in uitvoering")
                    else:
                        self.bezoeken.append(stap["doel"])
                        self._trace("service_klaar", doel=stap["doel"])
                        self.positie["na_service"] = stap["doel"]
                        self.stapindex += 1
                        self._service_sinds = None
                        self._kies_stap(p)
            elif self.toestand == "ZOEKEN":
                zoektijd = self._actief_ms - self._zoek_sinds
                if zoektijd >= self.instellingen["positie_onzeker_ms"]:
                    self.positie["status"] = "onzeker"
                if zoektijd >= self.instellingen.get("zoek_timeout_ms", 8000):
                    self._stop("Lijn/positie niet hersteld binnen zoek_timeout_ms")
                    self._meld_status(nu_ms)
                    return
                if lijnvolger.gewone_lijn(p) and self.positie["status"] != "onzeker":
                    if self._stabiel is None:
                        self._stabiel = self._actief_ms
                    if self._actief_ms - self._stabiel >= self.instellingen["lijn_ms"]:
                        self.toestand = "RIJDEN"
                        self._fase = getattr(self, "_fase_voor_zoeken", None)
                        self._stabiel = None
                        lijnvolger.reset_pid(self._pid)
                else:
                    self._stabiel = None
                self._motor(*lijnvolger.draaicommando(self._pid["richting"], self.instellingen["zoeken"]))
            elif self._beweging is not None:
                self._doe_beweging(p)
            elif self.positie["op_knoop"]:
                self._kies_stap(p)
            elif self._verwacht is not None:
                self._rijden(nu_ms, meting)
            else:
                self._stop("Geen actieve uitgang of verbinding")
        self._meld_status(nu_ms)

    def status(self):
        return {"bron": self.mqtt.bron, "toestand": self.toestand, "reden": self.reden,
                "mission_id": self.opdracht["mission_id"] if self.opdracht else None,
                "revisie": self.opdracht["revisie"] if self.opdracht else 0,
                "kaartversie": self.planner.kaart.versie, "stapindex": self.stapindex,
                "positie": dict(self.positie), "bezocht": list(self.bezoeken),
                "wachtende_revisie": self.wachtend["revisie"] if self.wachtend else None,
                "resultaat": "succesvol" if self.toestand == "KLAAR" else "fout" if self._fout else None,
                "laatste_resultaat": self.laatste_resultaat}

    def _meld_status(self, nu):
        status = self.status()
        if status != self._laatste_status or config.verschil_ms(nu, self._vorige_status_ms) >= config.STATUS_INTERVAL_MS:
            if status != self._laatste_status:
                self._trace("status", toestand=self.toestand, reden=self.reden, resultaat=status["resultaat"])
            self.status_seq += 1
            self._laatste_status = status
            status = dict(status)
            status["status_seq"] = self.status_seq
            self.mqtt.publiceer_status(status)
            self._vorige_status_ms = nu