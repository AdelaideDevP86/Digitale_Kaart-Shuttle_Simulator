"""Logische route-uitvoering, onafhankelijk van Qt en zonder netwerk/hardware.

Dezelfde RitBesturing ontvangt synthetische lijnpatronen en bij een grafisch
bereikte knoop een expliciete simulatiewaarneming. Dit is geen sensorfysica.
"""
from pathlib import Path
from gedeeld import ParcoursKaart, RoutePlanner
from robot import config
from robot.kruispunt_detector import KruispuntDetector
from robot.rit_besturing import RitBesturing
from robot.robot_mqtt import RobotMqtt
from .geometrie import bemonster, lengte, op_pad


class Simulator:
    def __init__(self, kaartpad=None):
        self.kaartpad = Path(kaartpad) if kaartpad else Path(__file__).resolve().parents[1]/'data/parcours.json'
        self.kaart = ParcoursKaart.uit_bestand(str(self.kaartpad))
        self.planner = RoutePlanner(self.kaart)
        self.paden = {eid:bemonster(e['geometrie']) for eid,e in self.kaart.verbindingen.items()}
        self.reset()

    def reset(self):
        instellingen = dict(config.MQTT, broker=None)
        self.mqtt = RobotMqtt(instellingen, bron='simulatie')
        self.besturing = RitBesturing(self.planner,KruispuntDetector(),self.mqtt,
                                      lambda l,r:None,voor_robot=False)
        self.besturing.bevestig_start()
        self.nu = self.command_seq = self.passage_seq = self.missie_teller = 0
        self._rest = 0.0
        self.gepauzeerd = self.obstakel = self.lijn_kwijt = False
        self.voorbeeld_plan = None
        self._reis_key = self._draai_key = None
        self._reis_fractie = self._draai_ms = 0
        depot = self.kaart.knopen[self.kaart.depot]
        self.x,self.y,self.hoek = depot['x'],depot['y'],0
        self.meldingen = ['Klaar voor een rit vanuit het treindepot.']
        self._vorige_toestand = 'GEREED'
        self._vorige_bezoeken = []
        self._vorige_revisie = 0
        self._laatste_motoren = (0,0)

    def voorbeeld(self, doelen):
        b = self.besturing
        if b.toestand not in ('GEREED','KLAAR'):
            raise ValueError('Bekijk een nieuwe route voor vertrek of na afloop.')
        self.voorbeeld_plan = self.planner.plan(b.positie,list(doelen))
        return self.voorbeeld_plan

    def _stuur(self, actie, doelen=None):
        b = self.besturing
        self.command_seq += 1
        if actie == 'start':
            self.missie_teller += 1
            missie, revisie = 'sim-rit-'+str(self.missie_teller),1
        else:
            missie = b.opdracht['mission_id'] if b.opdracht else 'geen-rit'
            revisie = max(b.opdracht['revisie'] if b.opdracht else 0,
                          b.wachtend['revisie'] if b.wachtend else 0)+1
        cmd = dict(command_id='sim-cmd-'+str(self.command_seq), command_seq=self.command_seq,
                   robot_id=self.mqtt.robot_id,sessie_id=self.mqtt.sessie_id,
                   actie=actie,mission_id=missie,revisie=revisie,
                   kaartversie=self.kaart.versie,bestemmingen=list(doelen or []))
        self.mqtt.voer_in(cmd)
        ontvangen = self.mqtt.pak_opdracht()
        resultaat = b.ontvang(ontvangen) if ontvangen else {'resultaat':'gefilterd'}
        if resultaat['resultaat'] not in ('accepted','pending'):
            raise ValueError(resultaat.get('reden','Opdracht werd geweigerd.'))
        if actie == 'vervang':
            self.meldingen.append('Nieuwe route ontvangen; wacht op een geschikt routepunt.')
        elif actie == 'start':
            self.meldingen.append('Rit gestart: '+' → '.join(self.kaart.attracties[d]['naam'] for d in doelen)+ ' → Treindepot.')
        else:
            self.meldingen.append('Rit handmatig gestopt.')
        return resultaat

    def start(self, doelen):
        resultaat = self._stuur('start',doelen)
        self.gepauzeerd = False
        self.voorbeeld_plan = None
        self._vorige_bezoeken = []
        self._vorige_revisie = 0
        return resultaat

    def wijzig(self, doelen):
        return self._stuur('vervang',doelen)

    def stop(self):
        self._stuur('stop')
        self.gepauzeerd = False

    def stap(self, ms=100):
        """Expliciet stappen mag ook terwijl het afspelen gepauzeerd is."""
        self._vooruit(ms)

    def update(self, ms):
        if not self.gepauzeerd:
            self._vooruit(ms)

    def _vooruit(self, ms):
        if ms < 0 or ms > 5000:
            raise ValueError('Simulatiestap buiten bereik')
        self._rest += ms
        while self._rest >= 5:
            self._rest -= 5
            self._tik()

    def _tik(self):
        b = self.besturing
        # GEREED/KLAAR: geen verborgen voortgang van de ritklok.
        if b.toestand in ('GEREED','KLAAR','GESTOPT'):
            return
        self.nu += 5
        beweging = b._beweging
        sleutel = (id(b.plan),b.stapindex) if beweging else None
        if beweging and sleutel != self._draai_key:
            self._draai_key = sleutel
            self._draai_ms = 0
            self._draai_begin = self.hoek
        if beweging and not self.obstakel:
            self._draai_ms += 5
        patroon = '00100'
        if beweging and b._fase in ('UITLIJNEN','WIT'):
            patroon = '00000'
        elif beweging and b._fase == 'ZWART':
            minimum = config.RIJDEN['keer_min_ms'] if beweging['actie']=='keren' else 300
            patroon = '00100' if self._draai_ms >= minimum else '00000'
        if self.lijn_kwijt:
            patroon = '00000'
        b.update(self.nu,dict(patroon=patroon,obstakel=self.obstakel))
        if beweging and not self.obstakel:
            actie = beweging['actie']
            draai = {'links':-90,'rechts':90,'keren':-180}.get(actie,0)
            duur = config.RIJDEN['keer_min_ms'] if actie=='keren' else 300
            self.hoek = self._draai_begin + draai*min(1,self._draai_ms/duur)
        if b.toestand == 'ZOEKEN' and not self.obstakel:
            self.hoek -= .9
        key = (id(b.plan),b.stapindex,b._huidige_edge) if b._verwacht is not None else None
        if key is not None and key != self._reis_key:
            self._reis_key, self._reis_fractie = key,0.0
        elif (key is not None and b._beweging is None and b.toestand=='RIJDEN'
                and not self.obstakel and not self.lijn_kwijt):
            edge = self.kaart.verbindingen[b._huidige_edge]
            punten = self.paden[edge['id']]
            if b.positie['laatste_punt'] != edge['a']:
                punten = list(reversed(punten))
            # 45 schetseenheden per seconde; geen motor- of batterijmodel.
            self._reis_fractie = min(1,self._reis_fractie+45*.005/max(.001,lengte(punten)))
            self.x,self.y,self.hoek = op_pad(punten,self._reis_fractie)
            if self._reis_fractie >= 1:
                self.passage_seq += 1
                b.verwerk_waarneming(dict(knoop=b._verwacht,in_edge=b._huidige_edge,
                                          passage_seq=self.passage_seq))
        self._registreer()

    def _registreer(self):
        b = self.besturing
        if b.opdracht and b.opdracht['revisie'] != self._vorige_revisie:
            if self._vorige_revisie:
                self.meldingen.append('Nieuwe route actief vanaf het huidige routepunt.')
            self._vorige_revisie = b.opdracht['revisie']
        for doel in b.bezoeken:
            if doel not in self._vorige_bezoeken:
                self.meldingen.append('Bezoek afgerond: '+self.kaart.attracties[doel]['naam']+'.')
        self._vorige_bezoeken = list(b.bezoeken)
        if b.toestand != self._vorige_toestand:
            if b.toestand=='WACHTEN':
                self.meldingen.append('Aangekomen bij '+self.kaart.attracties[self.huidige_service()]['naam']+'; 5 seconden wachten.')
            elif b.toestand=='KLAAR':
                self.meldingen.append('Rit succesvol afgerond: terug bij het treindepot.')
            elif b.toestand=='GEBLOKKEERD':
                self.meldingen.append('Obstakel: beweging en haltetijd gepauzeerd.')
            elif b.toestand=='ZOEKEN':
                self.meldingen.append('Lijn kwijt: shuttle blijft zoeken.')
            self._vorige_toestand = b.toestand
        self.meldingen[:] = self.meldingen[-200:]

    def huidige_service(self):
        b = self.besturing
        wacht = b.toestand=='WACHTEN' or (b.toestand=='GEBLOKKEERD' and b.hervat_toestand=='WACHTEN')
        return b.plan['stappen'][b.stapindex]['doel'] if wacht and b.plan else None

    def beeld(self):
        b = self.besturing
        voorbeeld = self.voorbeeld_plan is not None and b.toestand in ('GEREED','KLAAR')
        plan = self.voorbeeld_plan if voorbeeld else b.plan
        service = self.huidige_service()
        wacht_over = max(0,5000-(b._actief_ms-b._service_sinds)) if service else 0
        return dict(status=b.status(),plan=plan,stapindex=-1 if voorbeeld else b.stapindex,
                    service=service,wacht_over_ms=wacht_over,nu_ms=self.nu,
                    x=self.x,y=self.y,hoek=self.hoek,gepauzeerd=self.gepauzeerd,
                    edge=b._huidige_edge,fractie=self._reis_fractie,
                    positie_onzeker=b.positie['status']=='onzeker',voorbeeld=voorbeeld)
