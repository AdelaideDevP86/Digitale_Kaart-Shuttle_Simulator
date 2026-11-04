import copy
import itertools
import json
from pathlib import Path
import unittest

from gedeeld import ParcoursKaart, RoutePlanner
from robot import config, lijnvolger, hardware
from robot.kruispunt_detector import KruispuntDetector
from robot.objectdetectie import ObjectDetectie
from robot.rit_besturing import RitBesturing
from robot.robot_mqtt import RobotMqtt

DATA = Path(__file__).resolve().parents[1]/'data/parcours.json'


class Proef:
    def __init__(self, fysiek=False, data=None):
        if data is None:
            data = json.loads(DATA.read_text(encoding='utf-8'))
        self.kaart = ParcoursKaart(data)
        self.mqtt = RobotMqtt(config.MQTT, 'test-sessie', 'robot' if fysiek else 'simulatie')
        self.motoren = []
        self.b = RitBesturing(RoutePlanner(self.kaart), KruispuntDetector(), self.mqtt,
                             lambda l, r: self.motoren.append((l, r)), voor_robot=fysiek)
        self.b.bevestig_start()
        self.nu, self.seq, self.passage = 0, 0, 0
        self.missies = 0

    def stuur(self, actie='start', doelen=None, revisie=1, **extra):
        self.seq += 1
        if actie == 'start':
            self.missies += 1
        cmd = dict(command_id='cmd-'+str(self.seq), command_seq=self.seq,
                   robot_id=self.mqtt.robot_id, sessie_id=self.mqtt.sessie_id,
                   actie=actie, mission_id='rit-'+str(self.missies), revisie=revisie,
                   kaartversie=self.kaart.versie,
                   bestemmingen=list(doelen or ['WILDWATER', 'FREEFALL']))
        cmd.update(extra)
        self.mqtt.voer_in(cmd)
        ontvangen = self.mqtt.pak_opdracht()
        return self.b.ontvang(ontvangen) if ontvangen else {'resultaat':'gefilterd'}

    def tik(self, p='00100', dt=5, **extra):
        self.nu += dt
        meting = dict(patroon=p)
        meting.update(extra)
        self.b.update(self.nu, meting)

    def verlaat(self):
        for _ in range(300):
            if self.b._beweging is None:
                return
            p = '00000' if self.b._fase in ('UITLIJNEN', 'WIT') else '00100'
            self.tik(p)
        raise AssertionError('Uitgang niet afgerond')

    def aankomst(self):
        self.passage += 1
        self.b.verwerk_waarneming(dict(knoop=self.b._verwacht, in_edge=self.b._huidige_edge,
                                       passage_seq=self.passage))

    def ronde(self):
        for _ in range(500):
            if self.b.toestand == 'KLAAR':
                return
            if self.b.toestand == 'WACHTEN':
                self.tik(dt=5000)
            elif self.b._beweging:
                self.verlaat()
            elif self.b._verwacht:
                self.aankomst()
            else:
                self.tik()
            if self.b.toestand in ('GESTOPT', 'ZOEKEN'):
                raise AssertionError(self.b.status())
        raise AssertionError('Rit niet afgerond')


class DetectorTests(unittest.TestCase):
    def test_een_passage_en_vrijgave(self):
        d = KruispuntDetector()
        self.assertIsNone(d.update(0, '00100'))
        d.update(25, '00100')
        self.assertIsNone(d.update(30, '11100'))
        self.assertEqual(d.update(40, '11100')['passage_seq'], 1)
        self.assertIsNone(d.update(1000, '11111'))
        d.update(1010, '00100'); d.update(1035, '00100')
        d.update(1040, '00111')
        self.assertEqual(d.update(1050, '00111')['passage_seq'], 2)

    def test_start_scheef_en_ruis_geen_valse_passage(self):
        d = KruispuntDetector()
        for t in range(0, 200, 5):
            self.assertIsNone(d.update(t, '00111'))
        self.assertTrue(lijnvolger.startlijn('00111'))
        self.assertTrue(lijnvolger.startlijn('11100'))
        self.assertFalse(lijnvolger.geldig('000111'))
        d.update(200, '00100'); d.update(225, '00100')
        d.update(230, '11100'); d.update(235, '00100')
        self.assertIsNone(d.update(240, '00100'))

    def test_pid_correctierichting_en_tijdsvenster(self):
        for patroon, kant in [('01000', 'links'), ('00010', 'rechts')]:
            s = lijnvolger.nieuwe_pid()
            l, r = lijnvolger.volg_lijn(patroon, 0, s, config.RIJDEN)
            self.assertEqual(s['richting'], kant)
            self.assertTrue(l < r if kant == 'links' else r < l)
            for t in range(5, 1000, 5):
                l, r = lijnvolger.volg_lijn('00100', t, s, config.RIJDEN)
                self.assertTrue(-.15 <= l <= .35 and -.15 <= r <= .35)
            self.assertLessEqual(len(s['historie']), 10)

    def test_objectdetectie_uit_en_hysterese(self):
        d = ObjectDetectie(config.OBJECT)
        self.assertFalse(d.update(0))
        c = dict(config.OBJECT, aan=True)
        d = ObjectDetectie(c)
        self.assertTrue(d.update(0))
        self.assertFalse(d.update(50, 300))
        self.assertTrue(d.update(100, 100))
        self.assertTrue(d.update(150, 200))
        self.assertFalse(d.update(200, 250))
        self.assertTrue(d.update(450, None))


class BesturingTests(unittest.TestCase):
    def test_325_complete_uitvoeringen_en_tweede_rit(self):
        doelen = ['FERRIS','ARCADE','WILDWATER','FREEFALL','COASTER']
        aantal = 0
        for lengte in range(1, 6):
            for volgorde in itertools.permutations(doelen, lengte):
                p = Proef()
                self.assertEqual(p.stuur(doelen=volgorde)['resultaat'], 'accepted')
                p.ronde()
                self.assertEqual(p.b.bezoeken, list(volgorde))
                self.assertEqual(p.b.status()['resultaat'], 'succesvol')
                self.assertEqual(p.b.motoren, (0, 0))
                aantal += 1
        self.assertEqual(aantal, 325)
        self.assertEqual(p.stuur(doelen=['ARCADE'])['resultaat'], 'accepted')
        p.ronde()
        self.assertEqual(p.b.bezoeken, ['ARCADE'])

    def bij_eerste_halte(self):
        p = Proef(); p.stuur()
        while p.b.toestand != 'WACHTEN':
            if p.b._beweging: p.verlaat()
            elif p.b._verwacht: p.aankomst()
            else: p.tik()
        return p

    def test_halte_vijf_sec_en_obstakelpauze(self):
        p = self.bij_eerste_halte()
        p.tik(dt=4990)
        self.assertEqual(p.b.toestand, 'WACHTEN')
        p.tik(dt=5, obstakel=True)
        p.tik(dt=10000, obstakel=True)
        self.assertEqual(p.b.toestand, 'GEBLOKKEERD')
        self.assertEqual(p.b.motoren, (0,0))
        p.tik(dt=5, obstakel=False)
        self.assertEqual(p.b.toestand, 'WACHTEN')
        p.tik(dt=10)
        self.assertEqual(p.b.bezoeken, ['WILDWATER'])
        self.assertNotEqual(p.b.toestand, 'WACHTEN')

    def test_wijziging_bij_halte_met_verplicht_vertrek(self):
        p = self.bij_eerste_halte()
        self.assertEqual(p.stuur('vervang', ['COASTER'], 2)['resultaat'], 'pending')
        p.tik(dt=5000)
        self.assertEqual(p.b.opdracht['revisie'], 2)
        self.assertEqual(p.b._beweging['servicevertrek'], 'WILDWATER')
        p.ronde()
        self.assertEqual(p.b.bezoeken, ['WILDWATER','COASTER'])

    def test_wijziging_tijdens_draaien_wacht_tot_volgende_knoop(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat(); p.aankomst()
        self.assertEqual(p.b.toestand, 'DRAAIEN')
        edge = p.b._beweging['via']
        p.stuur('vervang', ['COASTER'], 2)
        p.stuur('vervang', ['ARCADE'], 3)
        self.assertEqual(p.stuur('vervang', ['FREEFALL'], 2)['resultaat'], 'rejected')
        p.verlaat()
        self.assertEqual(p.b._huidige_edge, edge)
        self.assertEqual(p.b.opdracht['revisie'], 1)
        p.aankomst()
        self.assertEqual(p.b.opdracht['revisie'], 3)
        p.ronde()
        self.assertEqual(p.b.bezoeken, ['ARCADE'])

    def test_lang_zoeken_geen_timeout_succes_of_stap(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        index = p.b.stapindex
        p.tik('00000')
        p.tik('00000', dt=600000)
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        self.assertEqual(p.b.stapindex, index)
        self.assertEqual(p.b.positie['status'], 'onzeker')
        self.assertNotEqual(p.b.motoren, (0,0))
        self.assertIsNone(p.b.status()['resultaat'])
        p.stuur('stop')
        self.assertEqual(p.b.toestand, 'GESTOPT')
        self.assertEqual(p.b.motoren, (0,0))

    def test_verkeerd_punt_en_dubbel_event(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        p.aankomst()
        index = p.b.stapindex
        p.b.verwerk_waarneming(dict(knoop='J01', passage_seq=p.passage))
        self.assertEqual(p.b.stapindex, index)
        p.verlaat()
        p.passage += 1
        p.b.verwerk_waarneming(dict(knoop='D00', passage_seq=p.passage))
        self.assertEqual(p.b.toestand, 'ZOEKEN')
        self.assertIsNone(p.b.status()['resultaat'])

    def test_rechtdoor_passage_geen_meetstop(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        p.tik('00111'); p.tik('00111', dt=10); p.verlaat()
        # Nu over J01->J11. Rechtdoor op J11: alleen linker zijtak in rijrichting.
        voor = len(p.motoren)
        p.tik('11100'); p.tik('11100', dt=10)
        self.assertEqual(p.b._beweging['actie'], 'rechtdoor')
        self.assertTrue(all(m == (.35,.35) for m in p.motoren[voor:]))

    def test_fysieke_route_met_gesynthetiseerde_ankermetingen(self):
        # Validatievlaggen hieronder zijn UITSLUITEND invoer voor een softwaretest.
        data = json.loads(DATA.read_text(encoding='utf-8'))
        data['profiel'] = 'robot'
        data['depot_herkenning'] = dict(methode='anker', gevalideerd=True)
        for a in data['attracties']:
            a.update(herkenning='anker', gevalideerd=True)
        p = Proef(fysiek=True, data=data)
        self.assertEqual(p.stuur()['resultaat'], 'accepted')
        for _ in range(200):
            if p.b.toestand == 'KLAAR': break
            if p.b.toestand == 'WACHTEN': p.tik(dt=5000)
            elif p.b._beweging: p.verlaat()
            elif p.b._verwacht:
                if p.b._doel_methode() == 'anker':
                    p.tik(anker=p.b._verwacht)
                else:
                    richtingen = [p.kaart.beweging(p.b._verwacht,p.b._huidige_edge,e)
                                  for _,e in p.kaart.buren(p.b._verwacht) if e != p.b._huidige_edge]
                    patroon = ('11' if 'links' in richtingen else '00')+'1'+('11' if 'rechts' in richtingen else '00')
                    p.tik(patroon); p.tik(patroon,dt=10)
            else: p.tik()
            self.assertNotIn(p.b.toestand, ('GESTOPT','ZOEKEN'))
        self.assertEqual(p.b.toestand,'KLAAR')
        self.assertEqual(p.b.bezoeken,['WILDWATER','FREEFALL'])

    def test_kort_lijnverlies_hervat_zonder_stap_te_verbruiken(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        index = p.b.stapindex
        p.tik('00000'); p.tik('00100'); p.tik('00100',dt=25)
        self.assertEqual(p.b.toestand,'RIJDEN')
        self.assertEqual(p.b.stapindex,index)

    def test_depot_als_tussenliggende_keerplaats_geen_eindresultaat(self):
        data = json.loads(DATA.read_text(encoding='utf-8'))
        data['profiel']='robot'
        data['depot_herkenning']=dict(methode='anker',gevalideerd=True)
        for a in data['attracties']: a.update(herkenning='anker',gevalideerd=True)
        p = Proef(fysiek=True,data=data)
        p.b.positie = dict(laatste_punt='J01',in_edge='E02',op_knoop=True,status='route_aannemelijk')
        self.assertEqual(p.stuur(doelen=['FERRIS'])['resultaat'],'accepted')
        p.tik(); p.verlaat()
        self.assertEqual(p.b._verwacht,'D00')
        self.assertEqual(p.b._doel_methode(),'anker')
        p.tik(anker='D00')
        self.assertEqual(p.b._beweging['actie'],'keren')
        self.assertNotEqual(p.b.toestand,'KLAAR')
        self.assertIsNone(p.b.status()['resultaat'])

    def test_zwart_blok_eerst_volledig_en_lang_genoeg(self):
        data = json.loads(DATA.read_text(encoding='utf-8'))
        data['profiel']='robot'
        data['depot_herkenning']=dict(methode='zwart_blok',gevalideerd=True)
        for a in data['attracties']: a.update(herkenning='anker',gevalideerd=True)
        p = Proef(fysiek=True,data=data)
        p.b.positie=dict(laatste_punt='J01',in_edge='E02',op_knoop=True,status='route_aannemelijk')
        p.stuur(doelen=['FERRIS']); p.tik(); p.verlaat()
        p.tik('00111'); p.tik('00111',dt=10)
        self.assertIsNotNone(p.b._marker)
        p.tik('11111',dt=20); p.tik('11111',dt=499)
        self.assertEqual(p.b._verwacht,'D00')
        p.tik('11111',dt=1)
        self.assertEqual(p.b._beweging['actie'],'keren')
        self.assertIsNone(p.b.status()['resultaat'])

    def test_onuitvoerbare_wijziging_laat_bestaande_rit_intact(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat()
        oud = p.b.plan
        p.stuur('vervang',['COASTER'],2)
        p.kaart.blokkeer('E21')
        p.aankomst()
        self.assertIs(p.b.plan,oud)
        self.assertIsNone(p.b.wachtend)
        self.assertNotEqual(p.b.toestand,'GESTOPT')
        self.assertEqual(p.mqtt.uitgaande[-1]['resultaat'],'rejected')

    def test_obstakel_tijdens_draaien_hervat_zelfde_manouvre(self):
        p = Proef(); p.stuur(); p.tik(); p.verlaat(); p.aankomst()
        stap = p.b._beweging
        p.tik(obstakel=True); p.tik(dt=10000,obstakel=True)
        self.assertEqual(p.b.toestand,'GEBLOKKEERD')
        p.tik(obstakel=False)
        self.assertIs(p.b._beweging,stap)
        p.verlaat()
        self.assertEqual(p.b._huidige_edge,stap['via'])

    def test_onbevestigde_robotkaart_start_niet(self):
        p = Proef(fysiek=True)
        self.assertEqual(p.stuur()['resultaat'], 'rejected')
        self.assertEqual(p.b.toestand, 'GEREED')
        with self.assertRaises(ValueError):
            p.b.verwerk_waarneming(dict(knoop='D00'))

    def test_ongeldige_meting_stopt_motoren(self):
        p = Proef(); p.stuur(); p.tik()
        p.b.update(50, {'patroon':'000111'})
        self.assertEqual(p.b.motoren, (0,0))
        self.assertEqual(p.b.toestand, 'GESTOPT')


class HardwareTests(unittest.TestCase):
    def tearDown(self):
        hardware.sluit()

    def test_pwm_polariteit_en_nul_bij_opstarten(self):
        class Pin:
            IN, OUT = 0, 1
            def __init__(self, nummer, modus=None): self.nummer,self.waarde=nummer,0
            def value(self, waarde=None):
                if waarde is not None: self.waarde=waarde
                return self.waarde
        class PWM:
            def __init__(self,pin,freq,duty_u16): self.duty=duty_u16
            def duty_u16(self,waarde): self.duty=waarde
            def deinit(self): pass
        class Machine: pass
        Machine.Pin,Machine.PWM=Pin,PWM
        hardware.initialiseer(config.HARDWARE,Machine)
        self.assertTrue(all(p.duty == 0 for p in hardware._pwm))
        self.assertEqual(hardware.lees_meting()['patroon'],'11111')
        hardware.rijd(.35,.35)
        self.assertEqual([p.waarde for p in hardware._richting],[1,0])
        hardware.rijd(-.35,-.35)
        self.assertEqual([p.waarde for p in hardware._richting],[0,1])
        hardware.stop()
        self.assertTrue(all(p.duty == 0 for p in hardware._pwm))
        with self.assertRaises(ValueError): hardware.rijd(2,0)


if __name__ == '__main__':
    unittest.main()
