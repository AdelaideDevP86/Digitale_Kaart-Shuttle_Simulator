"""Regressie: extra rechterzijde blokkeert bevestigde linkerzijde bij J12."""
import unittest

from tests.test_robot_baan import BaanProef


class KruispuntTerugwegTests(unittest.TestCase):
    def tik_reeks(self, p, patroon, ms):
        for _ in range(ms // 5):
            p.tik(patroon)

    def terug_vanaf_arcade(self):
        p = BaanProef()
        self.assertEqual(p.stuur(doelen=['ARCADE'])['resultaat'], 'accepted')
        for _ in range(100):
            if p.b._verwacht == 'J12' and p.b.bezoeken == ['ARCADE']:
                return p
            if p.b._beweging:
                p.verlaat()
            elif p.b.toestand == 'WACHTEN':
                p.tik('00000', dt=5000)
            elif p.b._verwacht and p.b._doel_methode() == 'lijneinde':
                p.tik('00000'); p.tik('00000', dt=p.b.instellingen['lijneinde_ms'])
            elif p.b._verwacht:
                p.naar_volgende_knoop()
            else:
                p.tik()
        self.fail('Geen terugweg vanaf Arcade')

    def test_logpatroon_j12_eerst_rechts_dan_beide_mag_rechtdoor(self):
        p = self.terug_vanaf_arcade()
        self.assertEqual(p.b.plan['stappen'][p.b.stapindex]['actie'], 'rechtdoor')
        self.tik_reeks(p, '00110', 300)
        self.tik_reeks(p, '00111', 100)  # Log: eerste event meldt rechts.
        self.assertIsNotNone(p.b._punt)
        self.assertEqual(p.b._verwacht, 'J12')
        self.tik_reeks(p, '11111', 100)  # Daarna is ook links bevestigbaar.
        self.assertEqual(p.b.toestand, 'RIJDEN')
        self.assertEqual(p.b._beweging['van'], 'J12')
        self.assertEqual(p.b._beweging['naar'], 'J11')
        self.assertEqual(p.b._beweging['actie'], 'rechtdoor')
        self.tik_reeks(p, '00100', 50)
        self.assertEqual(p.b._verwacht, 'J11')
        self.assertEqual(p.b.stapindex, 7)
        self.assertEqual(p.b.detector.passage_seq, 4)

    def test_alleen_verkeerde_zijde_bewijst_j12_niet(self):
        p = self.terug_vanaf_arcade()
        stap = p.b.stapindex
        self.tik_reeks(p, '00111', 300)
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.motoren, (0, 0))
        self.assertEqual(p.b.stapindex, stap)
        self.assertEqual(p.b._verwacht, 'J12')
        self.assertNotEqual(p.b.status()['resultaat'], 'succesvol')

    def test_breedte_zonder_uitgaande_lijn_rondt_geen_stap_af(self):
        p = self.terug_vanaf_arcade()
        stap = p.b.stapindex
        self.tik_reeks(p, '00111', 100)
        self.tik_reeks(p, '11111', 100)
        self.tik_reeks(p, '00000', 100)  # Ook aanwezig in de laatste log.
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        self.assertEqual(p.b.stapindex, stap)
        self.assertEqual(p.b.bezoeken, ['ARCADE'])
        self.assertNotEqual(p.b.status()['resultaat'], 'succesvol')

    def test_complete_terugweg_na_extra_rechterzijde(self):
        p = self.terug_vanaf_arcade()
        self.tik_reeks(p, '00111', 100)
        self.tik_reeks(p, '11111', 100)
        self.tik_reeks(p, '00100', 50)
        for _ in range(100):
            if p.b.toestand == 'KLAAR':
                break
            if p.b._beweging:
                p.verlaat()
            elif p.b._verwacht == 'D00':
                self.tik_reeks(p, '11111', p.b.instellingen['marker_ms'] + 10)
            elif p.b._verwacht:
                p.naar_volgende_knoop()
            else:
                p.tik()
            self.assertNotIn(p.b.toestand, ('GESTOPT', 'ZOEKEN'), p.b.status())
        self.assertEqual(p.b.toestand, 'KLAAR')
        self.assertEqual(p.b.bezoeken, ['ARCADE'])
        self.assertEqual(p.b.positie['laatste_punt'], 'D00')
        self.assertEqual(p.b.status()['resultaat'], 'succesvol')

    def test_geplande_bocht_vereist_nog_steeds_de_juiste_zijde(self):
        p = BaanProef(); p.stuur(); p.tik(); p.verlaat()
        # J01 vraagt rechts. Alleen links mag geen rechterbocht starten.
        self.tik_reeks(p, '11100', 100)
        self.assertIsNone(p.b._beweging)
        # Bij beide kanten is de gevraagde rechtertak nu wel bevestigd.
        self.tik_reeks(p, '11111', 30)
        self.assertEqual(p.b._beweging['actie'], 'rechts')
        self.assertEqual(p.b._beweging['van'], 'J01')
        self.assertEqual(p.b.detector.passage_seq, 1)

    def test_bestaande_uitzondering_laatste_t_naar_depot_blijft_werken(self):
        p = self.terug_vanaf_arcade()
        p.naar_volgende_knoop(); p.verlaat()
        p.naar_volgende_knoop(); p.verlaat()
        self.assertEqual(p.b._verwacht, 'J01')
        self.assertEqual(p.b.plan['stappen'][p.b.stapindex]['naar'], 'D00')
        # Bestaande aanpassing: vanaf de steel bewijst rechts de T ook als
        # de linker depotarm nog niet afzonderlijk door de sensor is gezien.
        self.tik_reeks(p, '00111', 20)
        self.assertEqual(p.b._beweging['van'], 'J01')
        self.assertEqual(p.b._beweging['naar'], 'D00')
        self.assertEqual(p.b._beweging['actie'], 'links')


if __name__ == '__main__':
    unittest.main()
