"""Integratieproeven van het centrale kaartbestand, uitsluitend op de PC."""
import itertools
import json
import math
from pathlib import Path
import unittest

from gedeeld import ParcoursKaart, RoutePlanner
from tests.test_kaart_planner import Referentie, startpositie

KAARTPAD = Path(__file__).resolve().parents[1] / 'data' / 'parcours.json'


class ParcoursDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with KAARTPAD.open(encoding='utf-8') as bestand:
            cls.data = json.load(bestand)
        cls.kaart = ParcoursKaart.uit_bestand(str(KAARTPAD))
        cls.planner = RoutePlanner(cls.kaart)
        cls.ref = Referentie(cls.data)

    def test_hele_baan_en_bekende_bestemmingen(self):
        self.assertEqual(self.kaart.valideer(), [])
        self.assertEqual(len(self.kaart.knopen), 27)
        self.assertEqual(len(self.kaart.verbindingen), 32)
        self.assertEqual(self.kaart.depot, 'D00')
        self.assertEqual(self.kaart.start_edge, 'E01')
        self.assertEqual(set(self.kaart.attracties),
                         {'FERRIS', 'ARCADE', 'WILDWATER', 'FREEFALL', 'COASTER'})

    def test_geometrie_sluit_op_de_knopen_aan(self):
        for edge in self.data['verbindingen']:
            with self.subTest(edge=edge['id']):
                geo = edge['geometrie']
                self.assertIn(geo['kind'], ('polyline', 'cubic_bezier'))
                punten = geo['points']
                if geo['kind'] == 'cubic_bezier':
                    self.assertEqual(len(punten), 4)
                else:
                    self.assertGreaterEqual(len(punten), 2)
                for punt in punten:
                    self.assertEqual(len(punt), 2)
                    self.assertTrue(all(type(v) in (int, float) and math.isfinite(v) for v in punt))
                a, b = self.kaart.knopen[edge['a']], self.kaart.knopen[edge['b']]
                self.assertEqual(punten[0], [a['x'], a['y']])
                self.assertEqual(punten[-1], [b['x'], b['y']])

    def test_tekenrichting_past_bij_de_lokale_poorten(self):
        for edge in self.data['verbindingen']:
            punten = edge['geometrie']['points']
            for reeks, poort in ((punten, edge['a_poort']),
                                 (list(reversed(punten)), edge['b_poort'])):
                with self.subTest(edge=edge['id'], poort=poort):
                    begin = reeks[0]
                    naast = next(p for p in reeks[1:] if p != begin)
                    dx, dy = naast[0] - begin[0], naast[1] - begin[1]
                    self.assertTrue({'N': dx == 0 and dy < 0,
                                     'E': dx > 0 and dy == 0,
                                     'S': dx == 0 and dy > 0,
                                     'W': dx < 0 and dy == 0}[poort])

    def test_alle_325_bestemmingsvolgorden_op_het_centrale_bestand(self):
        aantal = 0
        for lengte in range(1, 6):
            for selectie in itertools.permutations(sorted(self.kaart.attracties), lengte):
                with self.subTest(doelen=selectie):
                    plan = self.planner.plan(startpositie(), list(selectie))
                    self.assertEqual(self.planner.valideer_plan(plan), [])
                    self.assertEqual([s['doel'] for s in plan['stappen'] if s['soort'] == 'service'], list(selectie))
                    self.assertEqual(plan['stappen'][-1]['knoop'], 'D00')
                aantal += 1
        self.assertEqual(aantal, 325)

    def test_4096_aanritgevallen_tegen_onafhankelijke_referentie(self):
        aantal = 0
        for start in self.ref.knopen:
            for _, inkomend in self.ref.adj[start]:
                for doel in self.ref.knopen:
                    for _, doel_in in self.ref.adj[doel]:
                        with self.subTest(start=start, in_edge=inkomend, doel=doel, doel_in=doel_in):
                            pad = self.planner.pad(start, inkomend, doel, doel_in)
                            self.assertEqual(len(pad), self.ref.afstand(start, inkomend, doel, doel_in))
                            einde = pad[-1]['naar'] if pad else start
                            aanrit = pad[-1]['via'] if pad else inkomend
                            self.assertEqual((einde, aanrit), (doel, doel_in))
                        aantal += 1
        self.assertEqual(aantal, 4096)

    def test_logisch_profiel_wordt_niet_als_robotprofiel_gebruikt(self):
        if self.kaart.profiel == 'logisch':
            with self.assertRaises(ValueError):
                self.planner.plan(startpositie(), ['WILDWATER'], voor_robot=True)


if __name__ == '__main__':
    unittest.main()
