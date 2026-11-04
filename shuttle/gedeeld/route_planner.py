"""Richtingbewuste routeplanning, zonder motor-, sensor- of MQTT-code.

Elke verbinding kost voorlopig 1. BFS vindt het kleinste aantal verbindingen
binnen de vaste aankomst-/vertrekregels, niet de kortste afstand in meters.
"""


class RoutePlanner:
    def __init__(self, kaart):
        fouten = kaart.valideer()
        if fouten:
            raise ValueError("Ongeldige kaart: " + "; ".join(fouten))
        self.kaart = kaart

    def _richting_controleren(self, knoop, in_edge):
        if not isinstance(knoop, str) or knoop not in self.kaart.knopen:
            raise ValueError("Onbekende knoop: " + str(knoop))
        if in_edge is None:
            if knoop != self.kaart.depot:
                raise ValueError("Aankomstrichting ontbreekt buiten het depot")
        else:
            if not isinstance(in_edge, str):
                raise ValueError("in_edge moet een verbinding-ID zijn")
            self.kaart.andere_kant(knoop, in_edge)

    def _positie_controleren(self, positie):
        if not isinstance(positie, dict):
            raise ValueError("Positie moet een dictionary zijn")
        if positie.get("op_knoop") is not True:
            raise ValueError("Een nieuwe route kan alleen starten op een knoop")
        status = positie.get("status")
        if status not in ("start_bevestigd", "depot_bevestigd", "route_aannemelijk"):
            raise ValueError("Positie is niet voldoende bekend om te plannen")
        knoop, in_edge = positie.get("laatste_punt"), positie.get("in_edge")
        self._richting_controleren(knoop, in_edge)
        if in_edge is None and status != "start_bevestigd":
            raise ValueError("Alleen een bevestigde depotstart mag zonder in_edge")
        resultaat = {"laatste_punt": knoop, "in_edge": in_edge,
                     "op_knoop": True, "status": status}
        if "na_service" in positie:
            doel_id = positie["na_service"]
            if not isinstance(doel_id, str):
                raise ValueError("na_service moet een attractie-ID zijn")
            profiel = self.kaart.serviceprofiel(doel_id)
            if knoop != profiel["doelknoop"] or in_edge != profiel["aankomst_edge"]:
                raise ValueError("na_service past niet bij de opgegeven positie")
            resultaat["na_service"] = doel_id
        return resultaat

    def _bestemmingen_controleren(self, bestemmingen):
        if not isinstance(bestemmingen, list) or not 1 <= len(bestemmingen) <= 5:
            raise ValueError("Geef een lijst met 1 t/m 5 bestemmingen")
        gezien = set()
        for doel_id in bestemmingen:
            if not isinstance(doel_id, str) or doel_id not in self.kaart.attracties:
                raise ValueError("Onbekende attractie: " + str(doel_id))
            if doel_id in gezien:
                raise ValueError("Dubbele bestemming: " + doel_id)
            gezien.add(doel_id)
        return list(bestemmingen)

    def _mag_doorrijden(self, knoop, in_edge, uit_edge):
        if not self.kaart.actief(uit_edge):
            return False
        if in_edge is None:
            return knoop == self.kaart.depot and uit_edge == self.kaart.start_edge
        return (in_edge != uit_edge
                or self.kaart.knopen[knoop]["soort"] in ("depot", "eindpunt"))

    def _rijstap(self, knoop, in_edge, uit_edge, service_id=None):
        naast = self.kaart.andere_kant(knoop, uit_edge)
        if service_id is not None:
            profiel = self.kaart.serviceprofiel(service_id)
            if (profiel["doelknoop"] != knoop or profiel["aankomst_edge"] != in_edge
                    or profiel["vertrek_edge"] != uit_edge):
                raise ValueError("Verkeerde vertrekbeweging na " + service_id)
            if not self.kaart.actief(uit_edge):
                raise ValueError("Verplichte vertrekverbinding is gesloten: " + uit_edge)
        elif not self._mag_doorrijden(knoop, in_edge, uit_edge):
            raise ValueError("Niet toegestane beweging op " + knoop)
        actie = self.kaart.beweging(knoop, in_edge, uit_edge)
        if actie in ("vertrek", "keren"):
            soort = actie
        elif self.kaart.knopen[knoop]["soort"] == "hoek":
            soort = "hoek"
        else:
            soort = "keuze"
        return {"soort": soort, "van": knoop, "via": uit_edge, "naar": naast,
                "actie": actie, "servicevertrek": service_id}

    def pad(self, start, in_edge, doel, doel_in=None):
        """Geef alleen rijstappen, of ValueError als geen toegestaan pad bestaat.

        De toestand bewaart ook de inkomende edge. Het doel is pas bereikt als
        de aanrit klopt. Daardoor wordt dezelfde knoop niet altijd hetzelfde
        behandeld, en werkt ook de terugweg na een halte.
        """
        self._richting_controleren(start, in_edge)
        if not isinstance(doel, str) or doel not in self.kaart.knopen:
            raise ValueError("Onbekend doelpunt: " + str(doel))
        if doel_in is not None:
            if not isinstance(doel_in, str):
                raise ValueError("doel_in moet een verbinding-ID zijn")
            self.kaart.andere_kant(doel, doel_in)
        begin = (start, in_edge)
        wachtrij, vorige = [begin], {begin: None}
        leesindex = 0
        gevonden = None
        # Een lijst met leesindex werkt ook op MicroPython: geen deque nodig.
        while leesindex < len(wachtrij):
            toestand = wachtrij[leesindex]
            leesindex += 1
            knoop, inkomend = toestand
            if knoop == doel and (doel_in is None or inkomend == doel_in):
                gevonden = toestand
                break
            for naast, uit_edge in self.kaart.buren(knoop):
                if not self._mag_doorrijden(knoop, inkomend, uit_edge):
                    continue
                volgende = (naast, uit_edge)
                if volgende not in vorige:
                    vorige[volgende] = (toestand, uit_edge)
                    wachtrij.append(volgende)
        if gevonden is None:
            raise ValueError("Geen toegestane route van " + start + " naar " + doel)
        stappen = []
        while gevonden != begin:
            ouder, uit_edge = vorige[gevonden]
            stappen.append(self._rijstap(ouder[0], ouder[1], uit_edge))
            gevonden = ouder
        stappen.reverse()
        return stappen

    def plan(self, positie, bestemmingen, voor_robot=False):
        """Plan bezoeken in opgegeven volgorde, eenmaal 5 s service, dan depot.

        Geen invoer wordt gewijzigd. Het resultaat geeft geplande acties, geen
        bewijs van werkelijk uitgevoerde bezoeken. Dat bewijs levert de robot.
        """
        start = self._positie_controleren(positie)
        doelen = self._bestemmingen_controleren(bestemmingen)
        if type(voor_robot) is not bool:
            raise ValueError("voor_robot moet True of False zijn")
        if voor_robot:
            controle = doelen + ([start["na_service"]] if "na_service" in start else [])
            self.kaart.controleer_robotprofiel(controle)
        knoop, inkomend = start["laatste_punt"], start["in_edge"]
        vertrek_na = start.get("na_service")
        stappen = []
        # None is de laatste etappe: terug naar het depot, zonder attractieservice.
        for doel_id in doelen + [None]:
            if vertrek_na is not None:
                profiel = self.kaart.serviceprofiel(vertrek_na)
                stap = self._rijstap(knoop, inkomend, profiel["vertrek_edge"], vertrek_na)
                stappen.append(stap)
                knoop, inkomend = stap["naar"], stap["via"]
                vertrek_na = None
            if doel_id is None:
                doel, doel_in = self.kaart.depot, None
            else:
                profiel = self.kaart.serviceprofiel(doel_id)
                doel, doel_in = profiel["doelknoop"], profiel["aankomst_edge"]
            for stap in self.pad(knoop, inkomend, doel, doel_in):
                stappen.append(stap)
                knoop, inkomend = stap["naar"], stap["via"]
            if doel_id is None:
                stappen.append({"soort": "einde", "knoop": self.kaart.depot})
            else:
                stappen.append({"soort": "service", "doel": doel_id, "knoop": doel,
                                "aankomst_edge": profiel["aankomst_edge"],
                                "vertrek_edge": profiel["vertrek_edge"], "wacht_ms": 5000})
                vertrek_na = doel_id
        for index, stap in enumerate(stappen):
            stap["index"] = index
        resultaat = {"schema_versie": 1, "kaartversie": self.kaart.versie,
                     "voor_robot": voor_robot, "start": start,
                     "bestemmingen": doelen, "stappen": stappen}
        return resultaat

    def valideer_plan(self, plan):
        """Controleer een heel plan opnieuw, bijvoorbeeld vlak voor installatie.

        Retourneert [] of een foutmeldingenlijst. Een nette lijst met onjuiste
        afslagen, ontbrekende service of alleen een eindstap is niet geldig.
        """
        try:
            self._controleer_plan(plan)
        except (ValueError, TypeError, KeyError, IndexError) as fout:
            return ["Ongeldig plan: " + str(fout)]
        return []

    def _controleer_plan(self, plan):
        if not isinstance(plan, dict):
            raise ValueError("plan moet een dictionary zijn")
        if type(plan.get("schema_versie")) is not int or plan["schema_versie"] != 1:
            raise ValueError("onbekende schema_versie")
        if plan.get("kaartversie") != self.kaart.versie:
            raise ValueError("andere kaartversie")
        if type(plan.get("voor_robot")) is not bool:
            raise ValueError("voor_robot ontbreekt of is ongeldig")
        start = self._positie_controleren(plan.get("start"))
        doelen = self._bestemmingen_controleren(plan.get("bestemmingen"))
        if plan["voor_robot"]:
            controle = doelen + ([start["na_service"]] if "na_service" in start else [])
            self.kaart.controleer_robotprofiel(controle)
        stappen = plan.get("stappen")
        if not isinstance(stappen, list) or not stappen:
            raise ValueError("stappen ontbreken")
        knoop, inkomend = start["laatste_punt"], start["in_edge"]
        vertrek_na = start.get("na_service")
        bezocht = 0
        for index, stap in enumerate(stappen):
            if not isinstance(stap, dict) or type(stap.get("index")) is not int or stap["index"] != index:
                raise ValueError("verkeerd stapnummer")
            soort = stap.get("soort")
            if soort == "service":
                if vertrek_na is not None or bezocht >= len(doelen):
                    raise ValueError("onverwachte of dubbele service")
                doel_id = doelen[bezocht]
                profiel = self.kaart.serviceprofiel(doel_id)
                verwacht = {"doel": doel_id, "knoop": profiel["doelknoop"],
                            "aankomst_edge": profiel["aankomst_edge"],
                            "vertrek_edge": profiel["vertrek_edge"], "wacht_ms": 5000}
                if any(stap.get(k) != v for k, v in verwacht.items()):
                    raise ValueError("service komt niet overeen met het profiel")
                if knoop != profiel["doelknoop"] or inkomend != profiel["aankomst_edge"]:
                    raise ValueError("service niet via de vereiste aanrit bereikt")
                bezocht += 1
                vertrek_na = doel_id
            elif soort == "einde":
                if (index != len(stappen) - 1 or knoop != self.kaart.depot
                        or stap.get("knoop") != self.kaart.depot
                        or bezocht != len(doelen) or vertrek_na is not None):
                    raise ValueError("einde zonder bezoeken en depotterugkeer")
            elif soort in ("vertrek", "keuze", "hoek", "keren"):
                verwacht = self._rijstap(knoop, inkomend, stap.get("via"), vertrek_na)
                if any(stap.get(k) != v for k, v in verwacht.items()):
                    raise ValueError("rijstap, richting of servicevertrek klopt niet")
                knoop, inkomend = verwacht["naar"], verwacht["via"]
                vertrek_na = None
            else:
                raise ValueError("onbekende stapsoort")
        if stappen[-1].get("soort") != "einde":
            raise ValueError("depot-eindstap ontbreekt")
