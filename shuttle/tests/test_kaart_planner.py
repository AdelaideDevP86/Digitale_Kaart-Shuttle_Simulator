"""Kaart- en plannerproeven. Uitvoeren vanuit shuttle:

    python -m unittest discover -s tests -p test_kaart_planner.py -v

De fixture is een logische kaart van de foto, geen geteste robotafstelling.
De referentie gebruikt Dijkstra en leest de ruwe fixture, niet plannerhelpers.
"""

import copy
import heapq
import itertools
import json
from pathlib import Path
import unittest

from gedeeld import ParcoursKaart, RoutePlanner


FIXTURE = Path(__file__).parent / "fixtures" / "parcours_logisch.json"


def kaartgegevens():
    with FIXTURE.open(encoding="utf-8") as bestand:
        return json.load(bestand)


def startpositie():
    return {
        "laatste_punt": "D00",
        "in_edge": None,
        "op_knoop": True,
        "status": "start_bevestigd",
    }


def t_profiel():
    """Alternatieve testconfiguratie, GEEN fysiek goedgekeurde halte."""
    data = kaartgegevens()
    data["versie"] = "test-t-splitsing"
    for doel in data["attracties"]:
        if doel["id"] == "WILDWATER":
            doel.update(doelknoop="J13", aankomst_edge="E27", vertrek_edge="E26")
    return data


class Referentie:
    """Onafhankelijke lengtecontrole op de gerichte aankomsttoestanden."""

    def __init__(self, data):
        self.knopen = {k["id"]: k for k in data["knopen"]}
        self.edges = {e["id"]: e for e in data["verbindingen"]}
        self.adj = {n: [] for n in self.knopen}
        for edge in data["verbindingen"]:
            if not edge.get("actief", True):
                continue
            self.adj[edge["a"]].append((edge["b"], edge["id"]))
            self.adj[edge["b"]].append((edge["a"], edge["id"]))

    def afstand(self, start, incoming, doel, doel_in=None):
        queue = [(0, start, incoming or "")]
        bezocht = set()
        while queue:
            afstand, knoop, inc = heapq.heappop(queue)
            if (knoop, inc) in bezocht:
                continue
            bezocht.add((knoop, inc))
            if knoop == doel and (doel_in is None or inc == doel_in):
                return afstand
            for naast, eid in self.adj[knoop]:
                if eid == inc and self.knopen[knoop]["soort"] not in ("depot", "eindpunt"):
                    continue
                heapq.heappush(queue, (afstand + 1, naast, eid))
        return None


class KaartTests(unittest.TestCase):
    def setUp(self):
        self.data = kaartgegevens()
        self.kaart = ParcoursKaart(self.data)

    def test_volledige_fixture_en_json_inladen(self):
        kaart = ParcoursKaart.uit_bestand(str(FIXTURE))
        self.assertEqual(kaart.valideer(), [])
        self.assertEqual(len(kaart.knopen), 27)
        self.assertEqual(len(kaart.verbindingen), 32)
        self.assertEqual(len(kaart.attracties), 5)
        self.assertEqual(kaart.doelknoop("WILDWATER"), "S03")
        self.assertEqual(kaart.profiel, "logisch")

    def test_constructeur_verwerpt_ongeldige_kaarten(self):
        varianten = []
        data = kaartgegevens(); data.pop("versie"); varianten.append(data)
        data = kaartgegevens(); data["knopen"][0]["poorten"] = "EE"; varianten.append(data)
        data = kaartgegevens(); data["knopen"][0]["soort"] = []; varianten.append(data)
        data = kaartgegevens(); data["knopen"].append(copy.deepcopy(data["knopen"][0])); varianten.append(data)
        data = kaartgegevens(); data["verbindingen"].append(copy.deepcopy(data["verbindingen"][0])); varianten.append(data)
        data = kaartgegevens(); data["verbindingen"][0]["b"] = "BESTAAT_NIET"; varianten.append(data)
        data = kaartgegevens(); data["verbindingen"][0]["b"] = "D00"; varianten.append(data)
        data = kaartgegevens(); data["verbindingen"][1]["a_poort"] = "W"; varianten.append(data)
        data = kaartgegevens(); data["verbindingen"].pop(0); varianten.append(data)
        data = kaartgegevens(); data["verbindingen"][0]["actief"] = "false"; varianten.append(data)
        data = kaartgegevens(); data["depot"] = "ONBEKEND"; varianten.append(data)
        data = kaartgegevens(); data["start_edge"] = "E32"; varianten.append(data)
        data = kaartgegevens(); data["attracties"][0]["aankomst_edge"] = "E01"; varianten.append(data)
        data = kaartgegevens(); data["attracties"][0]["gevalideerd"] = 1; varianten.append(data)
        for i, data in enumerate(varianten):
            with self.subTest(variant=i), self.assertRaises(ValueError):
                ParcoursKaart(data)
        for data in (None, [], {}, {"knopen": "fout"}):
            with self.subTest(invoer=data), self.assertRaises(ValueError):
                ParcoursKaart(data)

    def test_richting_gebruikt_aankomstpoort(self):
        self.assertEqual(self.kaart.beweging("J01", "E01", "E14"), "rechts")
        self.assertEqual(self.kaart.beweging("J01", "E02", "E14"), "links")
        self.assertEqual(self.kaart.beweging("J01", "E01", "E02"), "rechtdoor")
        self.assertEqual(self.kaart.beweging("S03", "E28", "E28"), "keren")
        self.assertEqual(self.kaart.beweging("D00", None, "E01"), "vertrek")

    def test_buitenbocht_gebruikt_eindpoorten(self):
        # E19 verlaat beide uiteinden via poort N. Dit is een kromme lijn,
        # geen reden om automatisch tegenovergestelde poorten te verzinnen.
        self.assertEqual(self.kaart.poort("J04", "E19"), "N")
        self.assertEqual(self.kaart.poort("J15", "E19"), "N")
        self.assertEqual(self.kaart.beweging("J04", "E04", "E19"), "links")

    def test_buren_blokkeren_en_deblokkeren(self):
        self.assertIn(("S03", "E28"), self.kaart.buren("J13"))
        self.kaart.blokkeer("E28")
        self.assertNotIn(("S03", "E28"), self.kaart.buren("J13"))
        self.kaart.deblokkeer("E28")
        self.assertIn(("S03", "E28"), self.kaart.buren("J13"))
        for methode in (self.kaart.blokkeer, self.kaart.deblokkeer):
            with self.assertRaises(ValueError):
                methode("E_ONBEKEND")

    def test_deblokkeer_heft_vast_inactief_niet_op(self):
        self.data["verbindingen"][27]["actief"] = False  # E28
        kaart = ParcoursKaart(self.data)
        kaart.blokkeer("E28")
        kaart.deblokkeer("E28")
        self.assertFalse(kaart.actief("E28"))

    def test_registers_hebben_eigen_records(self):
        self.data["verbindingen"][0]["actief"] = False
        self.data["attracties"][2]["doelknoop"] = "J13"
        self.assertTrue(self.kaart.actief("E01"))
        self.assertEqual(self.kaart.doelknoop("WILDWATER"), "S03")
        profiel = self.kaart.serviceprofiel("WILDWATER")
        profiel["doelknoop"] = "J13"
        self.assertEqual(self.kaart.doelknoop("WILDWATER"), "S03")


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.data = kaartgegevens()
        self.kaart = ParcoursKaart(self.data)
        self.planner = RoutePlanner(self.kaart)
        self.ref = Referentie(self.data)

    def controleer_pad(self, stappen, start, inc, doel, doel_in=None):
        knoop = start
        for stap in stappen:
            self.assertEqual(stap["van"], knoop)
            edge = self.ref.edges[stap["via"]]
            self.assertIn(knoop, (edge["a"], edge["b"]))
            self.assertTrue(edge.get("actief", True))
            volgende = edge["b"] if knoop == edge["a"] else edge["a"]
            self.assertEqual(stap["naar"], volgende)
            if inc is not None and stap["via"] == inc:
                self.assertIn(self.ref.knopen[knoop]["soort"], ("depot", "eindpunt"))
            knoop, inc = volgende, stap["via"]
        self.assertEqual(knoop, doel)
        if doel_in is not None:
            self.assertEqual(inc, doel_in)

    def test_alle_richtingbewuste_start_doelgevallen(self):
        aantal = 0
        for start in self.ref.knopen:
            for _, incoming in self.ref.adj[start]:
                for doel in self.ref.knopen:
                    with self.subTest(start=start, incoming=incoming, doel=doel):
                        pad = self.planner.pad(start, incoming, doel)
                        self.controleer_pad(pad, start, incoming, doel)
                        self.assertEqual(len(pad), self.ref.afstand(start, incoming, doel))
                    aantal += 1
        self.assertEqual(aantal, 1728)

    def test_alle_verplichte_aankomstrichtingen(self):
        aantal = 0
        for start in self.ref.knopen:
            for _, incoming in self.ref.adj[start]:
                for doel in self.ref.knopen:
                    for _, doel_in in self.ref.adj[doel]:
                        with self.subTest(start=start, incoming=incoming, doel=doel, doel_in=doel_in):
                            pad = self.planner.pad(start, incoming, doel, doel_in)
                            self.controleer_pad(pad, start, incoming, doel, doel_in)
                            self.assertEqual(len(pad), self.ref.afstand(start, incoming, doel, doel_in))
                        aantal += 1
        self.assertEqual(aantal, 4096)

    def test_alle_325_attractievolgorden(self):
        doelen = [d["id"] for d in self.data["attracties"]]
        aantal = 0
        for lengte in range(1, 6):
            for selectie in itertools.permutations(doelen, lengte):
                with self.subTest(bestemmingen=selectie):
                    plan = self.planner.plan(startpositie(), list(selectie))
                    self.assertEqual(self.planner.valideer_plan(plan), [])
                    services = [s for s in plan["stappen"] if s["soort"] == "service"]
                    self.assertEqual([s["doel"] for s in services], list(selectie))
                    self.assertTrue(all(s["wacht_ms"] == 5000 for s in services))
                    self.assertEqual(plan["stappen"][-1]["soort"], "einde")
                    self.assertEqual(plan["stappen"][-1]["knoop"], "D00")
                    self.assertEqual([s["index"] for s in plan["stappen"]], list(range(len(plan["stappen"]))))
                aantal += 1
        self.assertEqual(aantal, 325)

    def test_kernroute_heeft_geen_extra_wildwaterbezoek(self):
        plan = self.planner.plan(startpositie(), ["WILDWATER", "FREEFALL"])
        services = [s for s in plan["stappen"] if s["soort"] == "service"]
        self.assertEqual([s["doel"] for s in services], ["WILDWATER", "FREEFALL"])
        self.assertEqual([s["knoop"] for s in services], ["S03", "S04"])
        self.assertEqual(plan["stappen"][-1]["knoop"], "D00")

    def test_hoek_en_keuze_blijven_aparte_stappen(self):
        plan = self.planner.plan(startpositie(), ["WILDWATER"])
        c03 = next(s for s in plan["stappen"] if s.get("van") == "C03")
        j09 = next(s for s in plan["stappen"] if s.get("van") == "J09")
        self.assertEqual(c03["soort"], "hoek")
        self.assertEqual(j09["soort"], "keuze")
        self.assertEqual(c03["actie"], "links")
        self.assertEqual(j09["actie"], "links")
        self.assertLess(c03["index"], j09["index"])

    def test_t_service_heeft_vaste_aanrit_en_vertrekedge(self):
        kaart = ParcoursKaart(t_profiel())
        planner = RoutePlanner(kaart)
        plan = planner.plan(startpositie(), ["WILDWATER", "FREEFALL"])
        service = next(s for s in plan["stappen"] if s["soort"] == "service")
        i = service["index"]
        self.assertEqual(service["knoop"], "J13")
        self.assertEqual(plan["stappen"][i - 1]["via"], "E27")
        self.assertEqual(plan["stappen"][i + 1]["via"], "E26")
        self.assertEqual(plan["stappen"][i + 1]["actie"], "rechts")
        self.assertEqual(planner.valideer_plan(plan), [])

    def test_service_mag_explicitiet_keren_op_keuzepunt(self):
        data = t_profiel()
        wildwater = next(d for d in data["attracties"] if d["id"] == "WILDWATER")
        wildwater["vertrek_edge"] = "E27"
        planner = RoutePlanner(ParcoursKaart(data))
        plan = planner.plan(startpositie(), ["WILDWATER"])
        i = next(s["index"] for s in plan["stappen"] if s["soort"] == "service")
        self.assertEqual(plan["stappen"][i + 1]["via"], "E27")
        self.assertEqual(plan["stappen"][i + 1]["actie"], "keren")
        self.assertEqual(planner.valideer_plan(plan), [])
        normaal = planner.pad("J13", "E27", "J09", "E27")
        self.assertGreater(len(normaal), 1)  # Gewone passage mag niet direct keren.
        self.assertNotEqual(normaal[0]["via"], "E27")

    def test_routewissel_na_service_behoudt_verplicht_vertrek(self):
        planner = RoutePlanner(ParcoursKaart(t_profiel()))
        positie = {"laatste_punt": "J13", "in_edge": "E27", "op_knoop": True,
                   "status": "route_aannemelijk", "na_service": "WILDWATER"}
        plan = planner.plan(positie, ["FREEFALL"])
        self.assertEqual(plan["stappen"][0]["via"], "E26")
        self.assertEqual(plan["stappen"][0]["actie"], "rechts")
        self.assertEqual(planner.valideer_plan(plan), [])
        self.assertEqual([s["doel"] for s in plan["stappen"] if s["soort"] == "service"], ["FREEFALL"])

    def test_na_service_met_verkeerde_positie_wordt_geweigerd(self):
        positie = startpositie()
        positie["na_service"] = "WILDWATER"
        with self.assertRaises(ValueError):
            self.planner.plan(positie, ["FREEFALL"])

    def test_onbereikbare_bestemming_en_depot_worden_gemeld(self):
        self.kaart.blokkeer("E28")
        with self.assertRaises(ValueError):
            self.planner.plan(startpositie(), ["WILDWATER"])
        self.kaart.deblokkeer("E28")
        self.kaart.blokkeer("E01")
        with self.assertRaises(ValueError):
            self.planner.plan(startpositie(), ["WILDWATER"])

    def test_geblokkeerde_servicevertrekedge_wordt_geweigerd(self):
        kaart = ParcoursKaart(t_profiel())
        kaart.blokkeer("E26")
        with self.assertRaises(ValueError):
            RoutePlanner(kaart).plan(startpositie(), ["WILDWATER", "FREEFALL"])

    def test_ongeldige_doelen_worden_geweigerd(self):
        for doelen in ([], ["ONBEKEND"], ["WILDWATER", "WILDWATER"], "WILDWATER", None,
                       ["FERRIS", "ARCADE", "WILDWATER", "FREEFALL", "COASTER", "FERRIS"]):
            with self.subTest(doelen=doelen), self.assertRaises(ValueError):
                self.planner.plan(startpositie(), doelen)

    def test_onzekere_of_verlaten_startknoop_wordt_geweigerd(self):
        varianten = []
        for veld, waarde in (("op_knoop", False), ("status", "onzeker"),
                             ("laatste_punt", "ONBEKEND"), ("in_edge", "E32")):
            pos = startpositie(); pos[veld] = waarde; varianten.append(pos)
        pos = startpositie(); pos.pop("op_knoop"); varianten.append(pos)
        pos = startpositie(); pos["laatste_punt"] = "J01"; varianten.append(pos)
        for positie in varianten + [None, []]:
            with self.subTest(positie=positie), self.assertRaises(ValueError):
                self.planner.plan(positie, ["WILDWATER"])

    def test_pad_verwerpt_niet_aansluitende_aankomstrichting(self):
        for args in (("J01", "E32", "S03"), ("J01", None, "S03"),
                     ("D00", None, "S03", "E01"), ("D00", None, "ONBEKEND")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.planner.pad(*args)

    def test_logische_plannen_worden_geen_robotplan(self):
        with self.assertRaises(ValueError):
            self.planner.plan(startpositie(), ["WILDWATER"], voor_robot=True)
        data = kaartgegevens(); data["profiel"] = "robot"
        planner = RoutePlanner(ParcoursKaart(data))
        with self.assertRaises(ValueError):
            planner.plan(startpositie(), ["WILDWATER"], voor_robot=True)

    def test_gevalideerd_robotprofiel_wordt_geaccepteerd(self):
        # Synthetische validatievlaggen voor een softwaretest; geen hardwarebewijs.
        data = kaartgegevens(); data["profiel"] = "robot"
        data["depot_herkenning"] = {"gevalideerd": True, "methode": "test-depot"}
        for doel in data["attracties"]:
            doel.update(gevalideerd=True, herkenning="test-service")
        planner = RoutePlanner(ParcoursKaart(data))
        plan = planner.plan(startpositie(), ["WILDWATER"], voor_robot=True)
        self.assertIs(plan["voor_robot"], True)
        self.assertEqual(planner.valideer_plan(plan), [])

    def test_plan_is_deterministisch_en_verandert_invoer_niet(self):
        positie, doelen = startpositie(), ["WILDWATER", "FREEFALL"]
        vooraf = copy.deepcopy((positie, doelen, self.data))
        een = self.planner.plan(positie, doelen)
        twee = self.planner.plan(positie, doelen)
        self.assertEqual(een, twee)
        self.assertEqual((positie, doelen, self.data), vooraf)
        een["bestemmingen"].append("ARCADE")
        een["stappen"][0]["actie"] = "fout"
        een["start"]["laatste_punt"] = "fout"
        self.assertEqual(self.planner.valideer_plan(twee), [])
        self.assertEqual(twee, self.planner.plan(positie, doelen))

    def test_plancontrole_verwerpt_beschadigde_plannen(self):
        origineel = self.planner.plan(startpositie(), ["WILDWATER", "FREEFALL"])
        varianten = []
        plan = copy.deepcopy(origineel); plan["stappen"][0]["index"] = 999; varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["stappen"][0]["actie"] = "links"; varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["kaartversie"] = "andere-kaart"; varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["stappen"].pop(); varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["stappen"][-1]["knoop"] = "S03"; varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["stappen"].append(copy.deepcopy(plan["stappen"][0])); varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["stappen"] = []; varianten.append(plan)
        plan = copy.deepcopy(origineel); plan["voor_robot"] = True; varianten.append(plan)
        for veld, waarde in (("wacht_ms", 0), ("aankomst_edge", "E01"),
                             ("vertrek_edge", "E01"), ("doel", "ARCADE")):
            plan = copy.deepcopy(origineel)
            service = next(s for s in plan["stappen"] if s["soort"] == "service")
            service[veld] = waarde
            varianten.append(plan)
        for i, plan in enumerate(varianten + [None, {}, {"stappen": None}]):
            with self.subTest(variant=i):
                fouten = self.planner.valideer_plan(plan)
                self.assertIsInstance(fouten, list)
                self.assertTrue(fouten)

    def test_bestaand_plan_wordt_ongeldig_na_blokkade(self):
        plan = self.planner.plan(startpositie(), ["WILDWATER"])
        self.assertEqual(self.planner.valideer_plan(plan), [])
        self.kaart.blokkeer(plan["stappen"][0]["via"])
        self.assertTrue(self.planner.valideer_plan(plan))


if __name__ == "__main__":
    unittest.main()
