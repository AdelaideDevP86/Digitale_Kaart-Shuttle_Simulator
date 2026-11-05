import math
import unittest
from simulatie.simulator import Simulator
from simulatie.geometrie import bemonster, lengte, op_pad


def afronden(sim):
    for _ in range(500):
        if sim.besturing.toestand=='KLAAR':return
        sim.update(500)
        if sim.besturing.toestand in ('GESTOPT','ZOEKEN'):
            raise AssertionError(sim.besturing.status())
    raise AssertionError('Geen voltooiing binnen 250 simulatieseconden')


class SimulatorTests(unittest.TestCase):
    def test_route_animatie_en_beide_haltes(self):
        s=Simulator();s.start(['WILDWATER','FREEFALL'])
        begin=(s.x,s.y)
        s.update(500)
        self.assertNotEqual((s.x,s.y),begin)
        afronden(s)
        self.assertEqual(s.besturing.bezoeken,['WILDWATER','FREEFALL'])
        self.assertEqual(s.besturing.status()['resultaat'],'succesvol')
        d=s.kaart.knopen[s.kaart.depot]
        self.assertAlmostEqual(s.x,d['x']);self.assertAlmostEqual(s.y,d['y'])
        self.assertTrue(any('5 seconden wachten' in m for m in s.meldingen))

    def test_alle_attracties_en_tweede_rit(self):
        s=Simulator();doelen=['COASTER','FREEFALL','WILDWATER','ARCADE','FERRIS']
        s.start(doelen);afronden(s)
        self.assertEqual(s.besturing.bezoeken,doelen)
        s.voorbeeld(['ARCADE'])
        self.assertTrue(s.beeld()['voorbeeld'])
        self.assertEqual(s.beeld()['plan']['bestemmingen'],['ARCADE'])
        s.start(['ARCADE']);afronden(s)
        self.assertEqual(s.besturing.bezoeken,['ARCADE'])

    def test_pauze_en_handmatig_stappen(self):
        s=Simulator();s.start(['ARCADE']);s.update(500)
        s.gepauzeerd=True
        beeld=s.beeld();s.update(1000)
        self.assertEqual((s.nu,s.x,s.y),(beeld['nu_ms'],beeld['x'],beeld['y']))
        s.stap(100)
        self.assertEqual(s.nu,beeld['nu_ms']+100)
        s.gepauzeerd=False;afronden(s)

    def test_obstakel_bevriest_positie_en_halte(self):
        s=Simulator();s.start(['WILDWATER'])
        for _ in range(100):
            if s.besturing.toestand=='WACHTEN':break
            s.update(100)
        self.assertEqual(s.besturing.toestand,'WACHTEN')
        s.obstakel=True;s.update(5)
        voor=s.beeld();s.update(5000)
        na=s.beeld()
        self.assertEqual(na['status']['toestand'],'GEBLOKKEERD')
        self.assertEqual(na['wacht_over_ms'],voor['wacht_over_ms'])
        self.assertEqual((na['x'],na['y']),(voor['x'],voor['y']))
        s.obstakel=False;afronden(s)

    def test_lijnverlies_zoekt_kort_en_stopt_bij_onzekerheid(self):
        s=Simulator();s.start(['ARCADE']);s.update(500)
        s.lijn_kwijt=True;s.update(1000)
        self.assertEqual(s.besturing.toestand,'ZOEKEN')
        s.update(1000)
        self.assertEqual(s.besturing.toestand,'GESTOPT')
        self.assertTrue(s.beeld()['positie_onzeker'])
        s.lijn_kwijt=False;s.update(1000)
        self.assertEqual(s.besturing.toestand,'GESTOPT')
        s.reset();self.assertEqual(s.besturing.toestand,'GEREED')
        self.assertFalse(s.beeld()['positie_onzeker'])

    def test_wijziging_onderweg_via_dezelfde_besturing(self):
        s=Simulator();s.start(['WILDWATER','FREEFALL']);s.update(1000)
        self.assertEqual(s.wijzig(['COASTER'])['resultaat'],'pending')
        afronden(s)
        self.assertEqual(s.besturing.bezoeken,['COASTER'])
        self.assertEqual(s.besturing.opdracht['revisie'],2)

    def test_netwerk_en_echte_hardware_worden_niet_gebruikt(self):
        s=Simulator()
        self.assertIsNone(s.mqtt.instellingen['broker'])
        self.assertEqual(s.mqtt.bron,'simulatie')
        self.assertFalse(s.besturing.voor_robot)
        s.start(['FERRIS']);s.update(200)
        self.assertIsNone(s.mqtt._sock)

    def test_bezier_en_tegengestelde_richting(self):
        s=Simulator();punten=s.paden['E19']
        self.assertGreater(len(punten),4)
        self.assertEqual(punten[0],(260,72));self.assertEqual(punten[-1],(371,118))
        x,y,h=op_pad(punten,.3)
        xx,yy,hh=op_pad(list(reversed(punten)),.7)
        self.assertAlmostEqual(x,xx);self.assertAlmostEqual(y,yy)
        self.assertAlmostEqual(abs(((h-hh+180)%360)-180),180)
        self.assertGreater(lengte(punten),math.hypot(111,46))


if __name__=='__main__':unittest.main()
