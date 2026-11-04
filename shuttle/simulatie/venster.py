"""PyQt6-bediening. Alle ritlogica blijft in Simulator en RitBesturing."""
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase
from pathlib import Path
import os
from PyQt6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QComboBox,QListWidget,QListWidgetItem,QCheckBox,QPlainTextEdit,
    QFrame,QScrollArea,QSplitter,QAbstractItemView)
from .simulator import Simulator
from .kaart_weergave import KaartWeergave

STIJL='''
QMainWindow,QWidget#root {background:#eef2f7;color:#18334e;}
QWidget {font-family:'Segoe UI';font-size:13px;color:#18334e;}
QFrame#card {background:white;border:1px solid #dce4ed;border-radius:12px;}
QLabel#title {font-size:25px;font-weight:700;}
QLabel#subtitle {color:#61758a;}
QLabel#heading {font-size:15px;font-weight:700;}
QLabel#value {font-size:22px;font-weight:650;}
QLabel#badge {background:#dff3ed;color:#14705d;border-radius:12px;padding:6px 13px;font-weight:600;}
QPushButton {background:white;border:1px solid #ccd6e1;border-radius:7px;padding:8px 10px;}
QPushButton:hover {background:#edf6f5;border-color:#098a80;}
QPushButton:disabled {background:#f3f5f8;color:#a4afbd;border-color:#e5eaf0;}
QPushButton#primary {background:#098a80;color:white;border-color:#098a80;font-weight:650;}
QPushButton#primary:hover {background:#08766e;}
QPushButton#primary:disabled {background:#b6d7d1;border-color:#b6d7d1;}
QPushButton#stop {color:#b14d41;}
QComboBox {background:white;border:1px solid #ccd6e1;border-radius:6px;padding:7px;}
QListWidget {background:#fafbfd;border:1px solid #e0e7ef;border-radius:7px;padding:3px;}
QListWidget::item {padding:6px;border-radius:4px;}
QListWidget::item:selected {background:#dff3ed;color:#126d62;}
QPlainTextEdit {background:#fafbfd;border:1px solid #e0e7ef;border-radius:7px;padding:5px;font-size:12px;}
QScrollArea {background:transparent;border:0;}
QCheckBox {spacing:7px;padding:3px;}
'''

_fonts_geladen=False


def bereid_lettertypen_voor():
    """Ook bruikbaar bij offscreen-tests zonder systeem-fontregistratie."""
    global _fonts_geladen
    if _fonts_geladen:return
    if 'Segoe UI' not in QFontDatabase.families():
        fontmap=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for naam in ('segoeui.ttf','segoeuib.ttf','seguisym.ttf'):
            pad=fontmap/naam
            if pad.is_file():QFontDatabase.addApplicationFont(str(pad))
    _fonts_geladen=True


def kaart(parent=None):
    frame=QFrame(parent);frame.setObjectName('card')
    layout=QVBoxLayout(frame);layout.setContentsMargins(16,14,16,14);layout.setSpacing(10)
    return frame,layout


def titel(tekst):
    label=QLabel(tekst);label.setObjectName('heading');return label


class Venster(QMainWindow):
    def __init__(self,simulator=None):
        super().__init__()
        bereid_lettertypen_voor()
        self.sim=simulator or Simulator()
        self.setWindowTitle('Parkshuttle — digitale parcourskaart')
        self.resize(1420,920);self.setMinimumSize(1060,730)
        self.setStyleSheet(STIJL)
        self._plan_key=None;self._log_tekst='';self._vorige_wachtende=None
        self._bouw()
        self._standaard_doelen()
        self.sim.voorbeeld(self.doelen())
        self._ververs()
        self.klok=QElapsedTimer();self.klok.start()
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick);self.timer.start(20)
        QTimer.singleShot(0,self.weergave.passend)

    def _bouw(self):
        root=QWidget();root.setObjectName('root');self.setCentralWidget(root)
        buiten=QVBoxLayout(root);buiten.setContentsMargins(24,20,24,20);buiten.setSpacing(16)
        kop=QHBoxLayout()
        naam=QVBoxLayout();label=QLabel('Parkshuttle');label.setObjectName('title');naam.addWidget(label)
        sub=QLabel('Plan een rit, volg de shuttle en probeer wijzigingen onderweg.');sub.setObjectName('subtitle');naam.addWidget(sub)
        kop.addLayout(naam);kop.addStretch()
        self.badge=QLabel('Simulatie');self.badge.setObjectName('badge');kop.addWidget(self.badge)
        buiten.addLayout(kop)
        splitter=QSplitter(Qt.Orientation.Horizontal);buiten.addWidget(splitter,1)
        links=QWidget();kolom=QVBoxLayout(links);kolom.setContentsMargins(0,0,12,0);kolom.setSpacing(12)
        samenvatting,rij=kaart();rij.setDirection(QVBoxLayout.Direction.LeftToRight)
        self.waarden={}
        for key,naam in [('bezoeken','BEZOEKEN'),('tijd','SIMULATIETIJD'),('halte','VOLGENDE HALTE')]:
            box=QVBoxLayout();box.setSpacing(4)
            label=QLabel(naam);label.setObjectName('subtitle');box.addWidget(label)
            waarde=QLabel('—');waarde.setObjectName('value');box.addWidget(waarde);self.waarden[key]=waarde
            rij.addLayout(box,1)
        self.waarden['halte'].setStyleSheet('font-size:18px;font-weight:650;')
        kolom.addWidget(samenvatting)
        canvas,layout=kaart()
        boven=QHBoxLayout();boven.addWidget(titel('Jouw parcours'));boven.addStretch()
        self.ids=QCheckBox('Puntnummers');boven.addWidget(self.ids)
        passend=QPushButton('Passend maken');passend.clicked.connect(lambda:self.weergave.passend());boven.addWidget(passend)
        layout.addLayout(boven)
        self.weergave=KaartWeergave(self.sim.kaart);self.weergave.setMinimumHeight(200)
        self.ids.toggled.connect(self.weergave.toon_ids);layout.addWidget(self.weergave,1)
        legend=QLabel('● Route &nbsp;&nbsp;&nbsp; <span style="color:#ed9a28">● Onderweg / halte</span> &nbsp;&nbsp;&nbsp; <span style="color:#26875d">● Bezocht</span>')
        legend.setStyleSheet('color:#098a80;font-size:12px;');layout.addWidget(legend)
        kolom.addWidget(canvas,1)
        log,loglayout=kaart();loglayout.addWidget(titel('Ritverloop'))
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setFixedHeight(94)
        loglayout.addWidget(self.log);kolom.addWidget(log)
        splitter.addWidget(links)
        rechts=QScrollArea();rechts.setWidgetResizable(True);rechts.setMinimumWidth(340)
        inhoud=QWidget();paneel=QVBoxLayout(inhoud);paneel.setContentsMargins(0,0,0,0);paneel.setSpacing(12)
        bediening,body=kaart()
        self.toestand=QLabel('Gereed');self.toestand.setObjectName('value');body.addWidget(self.toestand)
        self.onderschrift=QLabel();self.onderschrift.setWordWrap(True);self.onderschrift.setObjectName('subtitle');body.addWidget(self.onderschrift)
        body.addWidget(titel('Te bezoeken, in deze volgorde'))
        toevoegen=QHBoxLayout();self.attractie=QComboBox()
        for aid,a in self.sim.kaart.attracties.items(): self.attractie.addItem(a['naam'],aid)
        toevoegen.addWidget(self.attractie,1)
        knop=QPushButton('+');knop.setToolTip('Attractie toevoegen');knop.clicked.connect(lambda:self._actie(self._toevoegen));toevoegen.addWidget(knop)
        body.addLayout(toevoegen)
        self.bestemmingen=QListWidget();self.bestemmingen.setFixedHeight(142)
        self.bestemmingen.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        body.addWidget(self.bestemmingen)
        wijzigen=QHBoxLayout()
        for tekst,functie in [('Omhoog',lambda:self._verplaats(-1)),('Omlaag',lambda:self._verplaats(1)),('Verwijder',self._verwijder)]:
            knop=QPushButton(tekst);knop.clicked.connect(functie);wijzigen.addWidget(knop)
        body.addLayout(wijzigen)
        self.wijzig_button=QPushButton('Wijzig resterende route');self.wijzig_button.clicked.connect(lambda:self._actie(lambda:self.sim.wijzig(self.doelen())))
        body.addWidget(self.wijzig_button)
        rij=QHBoxLayout()
        self.preview_button=QPushButton('Route bekijken');self.preview_button.clicked.connect(lambda:self._actie(lambda:self.sim.voorbeeld(self.doelen())))
        self.start_button=QPushButton('Start rit');self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(lambda:self._actie(lambda:self.sim.start(self.doelen())))
        rij.addWidget(self.preview_button);rij.addWidget(self.start_button);body.addLayout(rij)
        rij=QHBoxLayout();self.pauze_button=QPushButton('Pauze');self.pauze_button.clicked.connect(self._pauze)
        self.stap_button=QPushButton('Stap +0,1 s');self.stap_button.clicked.connect(lambda:self._actie(lambda:self.sim.stap(100)))
        self.stop_button=QPushButton('Stop');self.stop_button.setObjectName('stop');self.stop_button.clicked.connect(lambda:self._actie(self.sim.stop))
        for knop in (self.pauze_button,self.stap_button,self.stop_button): rij.addWidget(knop)
        body.addLayout(rij)
        reset=QPushButton('Reset naar depot');reset.clicked.connect(self._reset);body.addWidget(reset)
        snelheid=QHBoxLayout();snelheid.addWidget(QLabel('Afspeelsnelheid'));snelheid.addStretch();self.snelheid=QComboBox()
        for factor in (1,2,5,10):self.snelheid.addItem(str(factor)+'×',factor)
        snelheid.addWidget(self.snelheid);body.addLayout(snelheid)
        self.bericht=QLabel('Kies bestemmingen en start de rit.');self.bericht.setWordWrap(True)
        body.addWidget(self.bericht);paneel.addWidget(bediening)
        testen,body=kaart();body.addWidget(titel('Test onderweg'))
        self.obstakel=QCheckBox('Obstakel op de baan');self.obstakel.toggled.connect(lambda aan:setattr(self.sim,'obstakel',aan));body.addWidget(self.obstakel)
        self.lijn=QCheckBox('Lijn kwijt');self.lijn.toggled.connect(lambda aan:setattr(self.sim,'lijn_kwijt',aan));body.addWidget(self.lijn)
        hint=QLabel('Bij langdurig lijnverlies wordt de positie onzeker. Reset daarna naar het depot.');hint.setWordWrap(True);hint.setObjectName('subtitle');body.addWidget(hint)
        paneel.addWidget(testen)
        stappen,body=kaart();body.addWidget(titel('Geplande ritstappen'))
        self.stappen=QListWidget();self.stappen.setMinimumHeight(140);self.stappen.setMaximumHeight(200)
        self.stappen.setWordWrap(True);body.addWidget(self.stappen);paneel.addWidget(stappen)
        paneel.addStretch();rechts.setWidget(inhoud);splitter.addWidget(rechts)
        splitter.setStretchFactor(0,1);splitter.setStretchFactor(1,0);splitter.setSizes([990,350])
        noot=QLabel('Logische simulatie van routes en ritbesturing · Wachttijden volgen de simulatietijd · Scroll op de kaart om te zoomen')
        noot.setObjectName('subtitle');noot.setStyleSheet('font-size:11px;');buiten.addWidget(noot)

    def doelen(self):
        return [self.bestemmingen.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.bestemmingen.count())]

    def _voeg_id_toe(self,aid):
        item=QListWidgetItem(self.sim.kaart.attracties[aid]['naam']);item.setData(Qt.ItemDataRole.UserRole,aid)
        self.bestemmingen.addItem(item)

    def _standaard_doelen(self):
        self.bestemmingen.clear()
        for aid in ('WILDWATER','FREEFALL'): self._voeg_id_toe(aid)

    def _toevoegen(self):
        aid=self.attractie.currentData()
        if aid in self.doelen(): raise ValueError('Deze attractie staat al in de lijst.')
        actief=self.sim.besturing.toestand not in ('GEREED','KLAAR','GESTOPT')
        if actief and (aid in self.sim.besturing.bezoeken or aid==self.sim.huidige_service()):
            raise ValueError('Deze attractie wordt al bezocht of is afgerond.')
        self._voeg_id_toe(aid)

    def _verwijder(self):
        rij=self.bestemmingen.currentRow()
        if rij>=0:self.bestemmingen.takeItem(rij)
        self._ververs()

    def _verplaats(self,richting):
        rij=self.bestemmingen.currentRow();nieuw=rij+richting
        if 0<=rij<self.bestemmingen.count() and 0<=nieuw<self.bestemmingen.count():
            item=self.bestemmingen.takeItem(rij);self.bestemmingen.insertItem(nieuw,item);self.bestemmingen.setCurrentRow(nieuw)
        self._ververs()

    def _actie(self,functie):
        try:
            uitkomst=functie()
            self.bericht.setStyleSheet('color:#14705d;')
            self.bericht.setText('Nieuwe route wacht op een geschikt routepunt.' if isinstance(uitkomst,dict) and uitkomst.get('resultaat')=='pending' else 'Opdracht verwerkt.')
        except ValueError as fout:
            self.bericht.setStyleSheet('color:#ae4639;');self.bericht.setText(str(fout))
        self._ververs()

    def _pauze(self):
        self.sim.gepauzeerd=not self.sim.gepauzeerd
        self._ververs()

    def _reset(self):
        self.sim.reset();self._plan_key=None
        self.obstakel.setChecked(False);self.lijn.setChecked(False)
        self._standaard_doelen();self.sim.voorbeeld(self.doelen())
        self.bericht.setStyleSheet('');self.bericht.setText('Shuttle teruggezet naar het depot.')
        self._ververs()

    def _tick(self):
        verstreken=min(100,self.klok.restart())
        try:
            self.sim.update(verstreken*self.snelheid.currentData())
            self._ververs()
        except Exception as fout:
            self.sim.gepauzeerd=True
            self.bericht.setStyleSheet('color:#ae4639;');self.bericht.setText('Test onderbroken: '+str(fout))

    def _ververs(self):
        beeld=self.sim.beeld();status=beeld['status'];toestand=status['toestand']
        actief=toestand not in ('GEREED','KLAAR','GESTOPT')
        if actief and self._vorige_wachtende and not status['wachtende_revisie']:
            toegepast=status['revisie']==self._vorige_wachtende
            self.bericht.setStyleSheet('color:#14705d;' if toegepast else 'color:#ae4639;')
            self.bericht.setText('Nieuwe route is nu actief.' if toegepast else 'Wijziging niet uitgevoerd; oorspronkelijke route blijft actief.')
        self._vorige_wachtende=status['wachtende_revisie']
        overslaan=set(status['bezocht']) if actief else set()
        if beeld['service']:overslaan.add(beeld['service'])
        # De lijst blijft de NOG te bezoeken doelen bevatten, ook tijdens service.
        for i in range(self.bestemmingen.count()-1,-1,-1):
            if self.bestemmingen.item(i).data(Qt.ItemDataRole.UserRole) in overslaan:
                self.bestemmingen.takeItem(i)
        namen={'GEREED':'Gereed voor vertrek','RIJDEN':'Onderweg','DRAAIEN':'Neemt een afslag',
               'WACHTEN':'Bij een attractie','ZOEKEN':'Zoekt de lijn','GEBLOKKEERD':'Wacht op vrij baan',
               'GESTOPT':'Rit gestopt','KLAAR':'Terug bij het depot'}
        self.toestand.setText('Gepauzeerd' if beeld['gepauzeerd'] else namen.get(toestand,toestand))
        detail='Kies de attracties in de gewenste volgorde.'
        if actief:
            detail='Volgt de geplande route naar het volgende punt.'
            if status['wachtende_revisie']:detail='Nieuwe route wacht op het volgende geschikte routepunt.'
            if beeld['service']:detail=f"Nog {beeld['wacht_over_ms']/1000:.1f} s bij deze attractie."
            if toestand=='GEBLOKKEERD':detail='Dezelfde actie gaat verder zodra het obstakel weg is.'
            if beeld['positie_onzeker']:detail='Positie onzeker. De shuttle blijft zoeken; reset voor een nieuwe rit.'
        elif toestand=='KLAAR':detail='Alle gevraagde bezoeken afgerond. Deze rit is succesvol.'
        elif toestand=='GESTOPT':detail='Reset naar depot om opnieuw te beginnen.'
        self.onderschrift.setText(detail)
        plan=beeld['plan']
        doelen=(plan['bestemmingen'] if plan else self.doelen()) if beeld['voorbeeld'] else self.sim.besturing.alle_doelen
        aantal=0 if beeld['voorbeeld'] else len(status['bezocht'])
        self.waarden['bezoeken'].setText(f"{aantal} / {len(doelen)}")
        seconden=beeld['nu_ms']//1000;self.waarden['tijd'].setText(f'{seconden//60:02d}:{seconden%60:02d}')
        volgende=beeld['service']
        if volgende is None and plan:
            for stap in plan['stappen'][max(0,beeld['stapindex']):]:
                if stap['soort']=='service':volgende=stap['doel'];break
        self.waarden['halte'].setText(self.sim.kaart.attracties[volgende]['naam'] if volgende else 'Treindepot')
        self.start_button.setEnabled(toestand in ('GEREED','KLAAR') and bool(self.doelen()))
        self.preview_button.setEnabled(toestand in ('GEREED','KLAAR') and bool(self.doelen()))
        self.wijzig_button.setEnabled(actief and bool(self.doelen()))
        self.pauze_button.setEnabled(actief);self.pauze_button.setText('Verder' if beeld['gepauzeerd'] else 'Pauze')
        self.stap_button.setEnabled(actief and beeld['gepauzeerd']);self.stop_button.setEnabled(actief)
        self.weergave.ververs(beeld)
        key=(id(plan),plan.get('kaartversie') if plan else None)
        if key!=self._plan_key:
            self._plan_key=key;self.stappen.clear()
            for stap in plan['stappen'] if plan else []:
                if stap['soort']=='service':tekst='5 sec bij '+self.sim.kaart.attracties[stap['doel']]['naam']
                elif stap['soort']=='einde':tekst='Rit afronden bij treindepot'
                else:
                    actie={'vertrek':'Vertrek','links':'Linksaf','rechts':'Rechtsaf','rechtdoor':'Rechtdoor','keren':'Keren'}[stap['actie']]
                    tekst=actie+' → '+self.sim.kaart.knopen[stap['naar']]['naam']
                self.stappen.addItem(tekst)
        rij=beeld['stapindex']
        if self.stappen.currentRow()!=rij:self.stappen.setCurrentRow(rij)
        tekst='\n'.join(self.sim.meldingen)
        if tekst!=self._log_tekst:
            self._log_tekst=tekst;self.log.setPlainText(tekst)
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def closeEvent(self,event):
        if hasattr(self,'timer'):self.timer.stop()
        super().closeEvent(event)
