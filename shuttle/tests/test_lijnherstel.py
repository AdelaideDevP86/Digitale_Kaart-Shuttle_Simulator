"""Regressies voor lijn voorbij draaien en vastlopen na een smal depotpatroon."""
import unittest

from robot import config, lijnvolger
from tests.test_besturing_detector import Proef
from tests.test_robot_baan import BaanProef
from tests import test_robot_baan as baanproeven


class LijnHerstelTests(unittest.TestCase):
    def op_edge(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        return p

    def na_laatste_afslag(self):
        p = baanproeven.DepotBinnenkomstTests().naar_laatste_afslag()
        p.verlaat()
        self.assertEqual(p.b._verwacht, 'D00')
        return p

    def test_gevonden_lijn_eerst_vastpakken_dan_zelfde_route_hervatten(self):
        p = self.op_edge()
        stap, edge = p.b.stapindex, p.b._huidige_edge
        p.tik('00000')
        self.assertNotEqual(p.b.motoren, (0, 0))
        p.tik('00100')
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        self.assertEqual(p.b.motoren, (0, 0))  # Niet verder over de lijn heen draaien.
        p.tik('00100', dt=25)
        self.assertEqual(p.b.toestand, 'RIJDEN')
        self.assertEqual(p.b.motoren, (.35, .35))
        self.assertEqual((p.b.stapindex, p.b._huidige_edge), (stap, edge))
        self.assertEqual(p.b.reden, '')

    def test_korte_gevonden_flits_is_nog_geen_hervatting(self):
        p = self.op_edge(); p.tik('00000')
        p.tik('00100'); p.tik('00000')
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        self.assertNotEqual(p.b.motoren, (0, 0))
        p.tik('00100'); p.tik('00100', dt=24)
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        p.tik('00100', dt=1)
        self.assertEqual(p.b.toestand, 'RIJDEN')

    def test_onzekerheid_stopt_zonder_nog_rondjes_te_maken(self):
        p = self.op_edge(); p.tik('00000')
        stap = p.b.stapindex
        p.tik('00100', dt=config.RIJDEN['positie_onzeker_ms'])
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.motoren, (0, 0))
        self.assertEqual(p.b.status()['resultaat'], 'fout')
        p.tik('00100', dt=1000)
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.stapindex, stap)

    def test_na_rechterbocht_zoeken_in_de_gekozen_richting(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat(); p.naar_volgende_knoop()
        self.assertEqual(p.b._beweging['actie'], 'rechts')
        p.verlaat(); p.tik('00000')
        self.assertEqual(p.b.motoren, (.35, -.35))

    def test_draai_remt_bij_nieuwe_lijn_in_zwartfase(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat(); p.naar_volgende_knoop()
        p.tik('00000', dt=config.RIJDEN['uitlijnen_ms'])
        p.tik('00000', dt=config.RIJDEN['lijn_ms'])
        self.assertEqual(p.b._fase, 'ZWART')
        p.tik('00100')
        self.assertEqual(p.b.motoren, (0, 0))
        self.assertEqual(p.b._fase, 'ZWART')
        p.tik('00100', dt=config.RIJDEN['lijn_ms'])
        self.assertEqual(p.b._fase, 'VERLATEN')
        self.assertEqual(p.b.motoren, (0, 0))

    def test_smal_depotpatroon_gevolgd_door_lijn_veroorzaakt_geen_fout(self):
        p = self.na_laatste_afslag()
        stap = p.b.stapindex
        p.tik('00111'); p.tik('00111', dt=10); p.tik('00100')
        self.assertEqual(p.b.toestand, 'RIJDEN')
        self.assertEqual(p.b.stapindex, stap)
        self.assertIsNone(p.b._marker)
        p.tik('01111'); p.tik('11110', dt=config.RIJDEN['marker_ms'])
        self.assertEqual(p.b.toestand, 'KLAAR')
        self.assertEqual(p.b.bezoeken, ['ARCADE'])

    def test_onderbroken_depotblok_reset_tijd_zonder_valse_aankomst(self):
        p = self.na_laatste_afslag()
        p.tik('11111'); p.tik('11111', dt=250)
        self.assertEqual(p.b.motoren, (0, 0))
        p.tik('00100')
        self.assertEqual(p.b.toestand, 'RIJDEN')
        p.tik('11111'); p.tik('11111', dt=config.RIJDEN['marker_ms']-1)
        self.assertNotEqual(p.b.toestand, 'KLAAR')
        p.tik('11111', dt=1)
        self.assertEqual(p.b.toestand, 'KLAAR')

    def test_d_term_heeft_geen_tienvoudige_opstartsprong(self):
        c = dict(config.RIJDEN, basis=1.0, min_motor=-10.0, kp=0.0, ki=0.0, kd=1.0)
        s = lijnvolger.nieuwe_pid()
        lijnvolger.volg_lijn('00100', 0, s, c)
        # Een halve schaal fout binnen een nog onvolledig 50ms-venster:
        # D is begrensd op 0,5, dus links=1-0,5; geen oude uitkomst -4.
        links, rechts = lijnvolger.volg_lijn('01000', 5, s, c)
        self.assertAlmostEqual(links, .5)
        self.assertAlmostEqual(rechts, 1.0)
        s = lijnvolger.nieuwe_pid()
        lijnvolger.volg_lijn('00100', 0, s, c)
        links, rechts = lijnvolger.volg_lijn('01000', 100, s, c)
        self.assertAlmostEqual(links, .75)  # Over 100 ms blijft de tijdschaling behouden.


if __name__ == '__main__':
    unittest.main()
