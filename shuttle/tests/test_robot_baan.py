"""Sensorreeksproeven voor de campusrit; geen bewijs van motor/sensorfysica."""
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from gedeeld import ParcoursKaart, RoutePlanner
from robot import config
from robot.kruispunt_detector import KruispuntDetector
from robot.main import controleer_start
from robot import main as robot_main
from robot.rit_log import RitLog
from tests.test_besturing_detector import Proef

ROBOTKAART = Path(__file__).resolve().parents[1] / 'data/parcours_robot.json'


class BaanProef(Proef):
    def __init__(self):
        super().__init__(fysiek=True, data=json.loads(ROBOTKAART.read_text(encoding='utf-8')))

    def naar_volgende_knoop(self):
        doel = self.b._verwacht
        richtingen = [self.kaart.beweging(doel, self.b._huidige_edge, edge)
                      for _, edge in self.kaart.buren(doel) if edge != self.b._huidige_edge]
        patroon = ('11' if 'links' in richtingen else '00') + '1' + ('11' if 'rechts' in richtingen else '00')
        for _ in range(60):
            self.tik(patroon)
            if self.b._verwacht != doel:
                return
        raise AssertionError(self.b.status())

    def bij_eerste_lijneinde(self):
        assert self.stuur()['resultaat'] == 'accepted'
        for _ in range(100):
            if self.b._beweging:
                self.verlaat()
            elif self.b._verwacht is None:
                self.tik()
            elif self.b._doel_methode() == 'lijneinde':
                return
            else:
                self.naar_volgende_knoop()
        raise AssertionError('Geen lijneinde in de route')


class RobotBaanTests(unittest.TestCase):
    def test_start_controleert_alleen_gevraagde_haltes(self):
        kaart = ParcoursKaart.uit_bestand(str(ROBOTKAART))
        controleer_start(kaart, ['WILDWATER', 'FREEFALL'])
        controleer_start(kaart, [])  # MQTT: doelen pas bij ontvangst controleren.
        controleer_start(kaart, ['FERRIS', 'ARCADE', 'COASTER'])  # alle vijf lijneinden
        self.assertEqual(kaart.doelknoop('WILDWATER'), 'S03')
        self.assertEqual(kaart.doelknoop('FREEFALL'), 'S04')

    def test_complete_sensorrit_twee_lijneinden_en_depot(self):
        p = BaanProef()
        self.assertEqual(p.stuur()['resultaat'], 'accepted')
        aankomsten, haltes = [], []
        for _ in range(200):
            if p.b.toestand == 'KLAAR':
                break
            if p.b._beweging:
                p.verlaat()
            elif p.b.toestand == 'WACHTEN':
                haltes.append(p.b.plan['stappen'][p.b.stapindex]['doel'])
                p.tik('00000', dt=4999)
                self.assertEqual(p.b.toestand, 'WACHTEN')
                self.assertEqual(p.b.motoren, (0, 0))
                p.tik('00000', dt=1)
                self.assertEqual(p.b._beweging['actie'], 'keren')
                self.assertEqual(p.b._fase, 'TERUG')
                self.assertTrue(p.b.motoren[0] < 0 and p.b.motoren[1] < 0)  # achteruit
                p.tik('00100')  # lijneinde weer onder de sensoren
                self.assertEqual(p.b.motoren, (0, 0))
                p.tik('00100', dt=25)  # stabiel teruggevonden voordat hij draait
                self.assertEqual(p.b._fase, 'WIT')
            elif p.b._verwacht:
                doel, methode = p.b._verwacht, p.b._doel_methode()
                aankomsten.append(doel)
                if methode == 'lijneinde':
                    p.tik('00000')
                    p.tik('00000', dt=config.RIJDEN['lijneinde_ms'])
                    self.assertEqual(p.b.toestand, 'WACHTEN')
                elif methode == 'zwart_blok':
                    p.tik('11111')
                    self.assertEqual(p.b.motoren, (0, 0))
                    p.tik('11111', dt=config.RIJDEN['marker_ms']-1)
                    self.assertNotEqual(p.b.toestand, 'KLAAR')
                    p.tik('11111', dt=1)
                else:
                    p.naar_volgende_knoop()
            else:
                p.tik()
            self.assertNotIn(p.b.toestand, ('GESTOPT', 'ZOEKEN'), p.b.status())
        self.assertEqual(p.b.toestand, 'KLAAR')
        self.assertEqual(haltes, ['WILDWATER', 'FREEFALL'])
        self.assertEqual(p.b.bezoeken, haltes)
        self.assertEqual(aankomsten.count('S03'), 1)
        self.assertEqual(aankomsten.count('S04'), 1)
        self.assertEqual(aankomsten[-1], 'D00')
        self.assertEqual(p.b.motoren, (0, 0))
        self.assertEqual(p.b.status()['resultaat'], 'succesvol')

    def test_terugrijden_bij_keren_is_begrensd(self):
        p = BaanProef(); p.bij_eerste_lijneinde()
        p.tik('00000'); p.tik('00000', dt=config.RIJDEN['lijneinde_ms'])
        self.assertEqual(p.b.toestand, 'WACHTEN')
        p.tik('00000', dt=5000)
        self.assertEqual(p.b._fase, 'TERUG')
        p.tik('00000', dt=config.RIJDEN['terug_max_ms'] - 10)
        self.assertEqual(p.b._fase, 'TERUG')      # nog geen lijn: blijft achteruit
        p.tik('00000', dt=10)
        self.assertEqual(p.b.toestand, 'GESTOPT')  # Zonder teruglijn niet blind draaien.
        self.assertEqual(p.b.motoren, (0, 0))

    def test_keertijd_telt_vanaf_draaien_niet_vanaf_terugrijden(self):
        # Rit 14:47: na 800 ms terugrijden accepteerde hij na 0,2 s draaien al de
        # lijn waar hij net vandaan kwam. De 700 ms minimum moet na het terugrijden gelden.
        p = BaanProef(); p.bij_eerste_lijneinde()
        p.tik('00000'); p.tik('00000', dt=config.RIJDEN['lijneinde_ms'])
        p.tik('00000', dt=5000)
        self.assertEqual(p.b._fase, 'TERUG')
        for _ in range((config.RIJDEN['terug_max_ms'] - 100) // 5):
            p.tik('00000')
        p.tik('00100'); p.tik('00100', dt=25)
        self.assertIn(p.b._fase, ('WIT', 'ZWART'))
        for _ in range(60):                 # 300 ms draaien: dichtbijgelegen lijn
            p.tik('00100' if _ > 20 else '00000')
        self.assertIn(p.b._fase, ('WIT', 'ZWART'))   # nog niet accepteren
        for _ in range(60): p.tik('00000')
        for _ in range(20): p.tik('00100')           # na ruim 700 ms: teruglijn
        p.tik('00100', dt=25)                       # lijn vasthouden tijdens bevestiging
        self.assertNotIn(p.b._fase, ('WIT', 'ZWART'))

    def test_witte_flits_aanrit_is_nog_geen_halte(self):
        p = BaanProef(); p.bij_eerste_lijneinde()
        index = p.b.stapindex
        p.tik('00000'); p.tik('00000', dt=99)
        self.assertEqual(p.b.toestand, 'RIJDEN')
        self.assertEqual(p.b.bezoeken, [])
        p.tik('00100')
        p.tik('00000'); p.tik('00000', dt=99)
        self.assertEqual(p.b.stapindex, index)
        p.tik('00000', dt=1)
        self.assertEqual(p.b.toestand, 'WACHTEN')

    def test_zijflits_telt_niet_en_late_rechtertak_wordt_afgewacht(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat()
        self.assertEqual(p.b._verwacht, 'J01')
        index, begin_motoren = p.b.stapindex, len(p.motoren)
        # Breed gedurende 10 ms, maar beide zijden eerst korter dan 10 ms.
        p.tik('11100'); p.tik('00111'); p.tik('11100')
        self.assertIsNotNone(p.b._punt)
        self.assertEqual(p.b.stapindex, index)
        self.assertEqual(p.b.toestand, 'RIJDEN')
        p.tik('00111'); p.tik('00111'); p.tik('00111')
        self.assertEqual(p.b._beweging['actie'], 'rechts')
        self.assertEqual(p.b.detector.passage_seq, 1)
        self.assertTrue(all(m == (.35, .35) for m in p.motoren[begin_motoren:]))

    def test_verkeerde_afslag_wordt_geen_verzonnen_aankomst(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat()
        index = p.b.stapindex
        p.tik('11100'); p.tik('11100', dt=10)
        self.assertEqual(p.b.toestand, 'RIJDEN')
        p.tik('11100', dt=config.RIJDEN['kruispunt_timeout_ms'])
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.stapindex, index)
        self.assertEqual(p.b.positie['laatste_punt'], 'D00')
        p.tik('00100', dt=config.RIJDEN['zoek_timeout_ms'])
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.status()['resultaat'], 'fout')

    def test_lijn_terug_binnen_1800ms_hervat_zelfde_edge(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat()
        index, edge = p.b.stapindex, p.b._huidige_edge
        p.tik('00000'); p.tik('00000', dt=1000)
        p.tik('00100'); p.tik('00100', dt=25)
        self.assertEqual(p.b.toestand, 'RIJDEN')
        self.assertEqual((p.b.stapindex, p.b._huidige_edge), (index, edge))

    def test_draaien_eindigt_bij_timeout_met_fout(self):
        for patroon in ('00100', '00000'):
            with self.subTest(patroon=patroon):
                p = BaanProef(); p.stuur(); p.tik(); p.verlaat(); p.naar_volgende_knoop()
                self.assertEqual(p.b.toestand, 'DRAAIEN')
                p.tik(patroon, dt=config.RIJDEN['beweging_timeout_ms'])
                self.assertEqual(p.b.toestand, 'GESTOPT')
                self.assertEqual(p.b.motoren, (0, 0))
                self.assertEqual(p.b.status()['resultaat'], 'fout')

    def test_obstakel_bevriest_zoek_timeout(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat(); p.tik('00000')
        p.tik('00000', obstakel=True); p.tik('00000', dt=100000, obstakel=True)
        p.tik('00000', obstakel=False)
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        p.tik('00100'); p.tik('00100', dt=25)
        self.assertEqual(p.b.toestand, 'RIJDEN')

    def test_black_block_buiten_depot_is_geen_succes(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat()
        p.tik('11111'); p.tik('11111', dt=10); p.tik('11111', dt=500)
        self.assertNotEqual(p.b.toestand, 'KLAAR')
        self.assertNotEqual(p.b.status()['resultaat'], 'succesvol')


class LogTests(unittest.TestCase):
    def test_ram_begrensd_en_schrijven_alleen_na_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            pad = Path(tmp) / 'ritlog.jsonl'
            log = RitLog(dict(config.LOG, pad=str(pad), events_max=3, metingen_max=2))
            p = BaanProef(); p.b.log = log; p.stuur(); p.tik()
            for n in range(10):
                log.event(n, 'proef', dict(n=n))
                log.meet(n*100, dict(patroon='00100'), p.b)
            self.assertFalse(pad.exists())
            self.assertEqual(len(log.events), 3)
            self.assertEqual(len(log.metingen), 2)
            with self.assertRaises(ValueError):
                log.schrijf(p.b)
            p.b._stop('testfout')
            self.assertTrue(log.schrijf(p.b))
            regels = [json.loads(r) for r in pad.read_text().splitlines()]
            self.assertEqual(len(regels), 5)
            self.assertEqual([r['seq'] for r in regels], sorted(r['seq'] for r in regels))
            self.assertEqual(regels[-1]['reden'], 'testfout')
            self.assertFalse(log.schrijf(p.b))


class HoofdloopTests(unittest.TestCase):
    def test_lokale_start_zonder_vijf_gevalideerde_attracties(self):
        with tempfile.TemporaryDirectory() as tmp:
            pad = str(Path(tmp) / 'ritlog.jsonl')
            with patch.object(config, 'KAARTPAD', str(ROBOTKAART)), \
                 patch.object(config, 'LOKALE_BESTEMMINGEN', ('WILDWATER', 'FREEFALL')), \
                 patch.object(config, 'START_WACHTTIJD_MS', 0, create=True), \
                 patch.object(config, 'LOG', dict(config.LOG, pad=pad)), \
                 patch.object(robot_main, 'verbind_wifi'), \
                 patch.object(robot_main.hardware, 'initialiseer') as init, \
                 patch.object(robot_main.hardware, 'rijd') as motor, \
                 patch.object(robot_main.hardware, 'stop') as stop, \
                 patch.object(robot_main.hardware, 'sluit'), \
                 patch.object(robot_main.hardware, 'lees_meting',
                              side_effect=[dict(patroon='00100'), KeyboardInterrupt]), \
                 redirect_stdout(StringIO()) as scherm:
                with self.assertRaises(KeyboardInterrupt):
                    robot_main.main()
                init.assert_called_once()
                stop.assert_called_once()
                self.assertIn((.35, .35), [call.args for call in motor.call_args_list])
                self.assertIn('LOKALE ROUTE: WILDWATER -> FREEFALL -> DEPOT', scherm.getvalue())
            regels = [json.loads(r) for r in Path(pad).read_text().splitlines()]
            self.assertTrue(any(r['soort'] == 'uitgang' for r in regels))

    def test_fout_profiel_stopt_en_logt_voor_motorinitialisatie(self):
        with tempfile.TemporaryDirectory() as tmp:
            pad = str(Path(tmp) / 'ritlog.jsonl')
            # Kopie van de robotkaart waarin COASTER (nog) niet gevalideerd is.
            data = json.loads(ROBOTKAART.read_text(encoding='utf-8'))
            for a in data['attracties']:
                if a['id'] == 'COASTER':
                    a.update(gevalideerd=False)
            kaartpad = Path(tmp) / 'kaart.json'
            kaartpad.write_text(json.dumps(data), encoding='utf-8')
            with patch.object(config, 'KAARTPAD', str(kaartpad)), \
                 patch.object(config, 'LOKALE_BESTEMMINGEN', ('COASTER',)), \
                 patch.object(config, 'LOG', dict(config.LOG, pad=pad)), \
                 patch.object(robot_main.hardware, 'initialiseer') as init, \
                 patch.object(robot_main.hardware, 'stop') as stop, \
                 patch.object(robot_main.hardware, 'sluit'):
                with self.assertRaisesRegex(ValueError, 'COASTER'):
                    robot_main.main()
                init.assert_not_called()
                stop.assert_called_once()
            regels = [json.loads(r) for r in Path(pad).read_text().splitlines()]
            self.assertEqual(regels[-1]['soort'], 'exception')


class DepotBinnenkomstTests(unittest.TestCase):
    """Ritten 16:00: het depotblok ligt vlak achter J01 en hij komt er soms schuin op."""

    def naar_laatste_afslag(self):
        p = BaanProef(); self.assertEqual(p.stuur(doelen=['ARCADE'])['resultaat'], 'accepted')
        for _ in range(3000):
            b = p.b
            if b._beweging and b._beweging['van'] == 'J01' and b._beweging['naar'] == 'D00':
                return p
            if b.toestand == 'WACHTEN':
                p.tik('00000', dt=5000)
            elif b._beweging:
                p.verlaat()
            elif b._verwacht and b._doel_methode() == 'lijneinde':
                p.tik('00000'); p.tik('00000', dt=config.RIJDEN['lijneinde_ms'])
            elif b._verwacht:
                p.naar_volgende_knoop()
            else:
                p.tik()
        raise AssertionError('Laatste afslag niet bereikt')

    def speel(self, reeks):
        p = self.naar_laatste_afslag()
        for patroon, ms in reeks:
            for _ in range(ms // 5):
                p.tik(patroon)
        return p.b

    def test_draaien_eindigt_op_het_blok(self):
        b = self.speel([('11111', 100), ('00000', 100), ('11000', 200), ('11111', 1200)])
        self.assertEqual(b.toestand, 'KLAAR')

    def test_schuin_op_het_blok_vier_van_vijf(self):
        b = self.speel([('11111', 100), ('00000', 300), ('01000', 100), ('00100', 150),
                        ('00111', 150), ('01111', 1000)])
        self.assertEqual(b.toestand, 'KLAAR')


    def naar_j01_vanaf_j11(self):
        p = BaanProef(); self.assertEqual(p.stuur(doelen=['ARCADE'])['resultaat'], 'accepted')
        for _ in range(3000):
            b = p.b
            if (b._verwacht == 'J01' and b._huidige_edge == 'E14'
                    and b.toestand == 'RIJDEN' and not b._beweging):
                return p
            if b.toestand == 'WACHTEN':
                p.tik('00000', dt=5000)
            elif b._beweging:
                p.verlaat()
            elif b._verwacht and b._doel_methode() == 'lijneinde':
                p.tik('00000'); p.tik('00000', dt=config.RIJDEN['lijneinde_ms'])
            elif b._verwacht:
                p.naar_volgende_knoop()
            else:
                p.tik()
        raise AssertionError('Stuk J11 -> J01 niet bereikt')

    def test_schuin_bij_j01_alleen_rechterarm_gezien(self):
        # Rit 16:24: de depotarm was al gepasseerd; de detector zag alleen 00111.
        p = self.naar_j01_vanaf_j11(); b = p.b
        for patroon, ms in [('00100', 50), ('01110', 50), ('00111', 60), ('00011', 100)]:
            for _ in range(ms // 5):
                p.tik(patroon)
        self.assertNotEqual(b.toestand, 'ZOEKEN', b.reden)
        self.assertEqual(b.positie['laatste_punt'], 'J01')
        for patroon, ms in [('00000', 200), ('11000', 100), ('00100', 200), ('11111', 1000)]:
            for _ in range(ms // 5):
                p.tik(patroon)
        self.assertEqual(b.toestand, 'KLAAR')


if __name__ == '__main__':
    unittest.main()