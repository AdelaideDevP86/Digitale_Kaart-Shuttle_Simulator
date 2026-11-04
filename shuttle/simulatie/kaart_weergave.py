"""De kaart tekent de echte JSON-geometrie; deze module kiest geen routes."""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPathItem

NAVY='#18334e'
TEAL='#098a80'
ORANGE='#ed9a28'
GREEN='#26875d'


def pen(kleur, breedte):
    p=QPen(QColor(kleur),breedte)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def maak_pad(geometrie):
    punten=geometrie['points']
    p=QPainterPath(QPointF(*punten[0]))
    if geometrie['kind']=='cubic_bezier':
        p.cubicTo(QPointF(*punten[1]),QPointF(*punten[2]),QPointF(*punten[3]))
    else:
        for punt in punten[1:]: p.lineTo(*punt)
    return p


class KaartWeergave(QGraphicsView):
    def __init__(self, kaart, parent=None):
        super().__init__(parent)
        self.kaart=kaart
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor('#fbfcfe'))
        self.setFrameShape(self.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.wegen,self.ids,self.stations,self.badges={},{},{},{}
        self._laatste_kleuren=None
        self._bouw()

    def _tekst(self, tekst,x,y,grootte=5,kleur=NAVY,vet=False):
        font=QFont('Segoe UI')
        font.setPointSizeF(grootte)
        font.setBold(vet)
        item=self.scene().addSimpleText(tekst,font)
        item.setBrush(QColor(kleur));item.setPos(x,y);item.setZValue(4)
        return item

    def _bouw(self):
        s=self.scene()
        for eid,e in self.kaart.verbindingen.items():
            item=s.addPath(maak_pad(e['geometrie']),pen('#cbd4df',5))
            item.setToolTip(eid+' · '+e['a']+' ↔ '+e['b'])
            self.wegen[eid]=item
        for nid,k in self.kaart.knopen.items():
            x,y=k['x'],k['y']
            r=2 if k['soort'] in ('keuze','hoek') else 4.2
            item=s.addEllipse(x-r,y-r,2*r,2*r,pen('#ffffff',.7),QBrush(QColor(NAVY)))
            item.setZValue(2);item.setToolTip(nid+' · '+k['naam'])
            label=self._tekst(nid,x+3,y+2,3.6,'#61758a')
            label.setVisible(False);self.ids[nid]=label
        depot=self.kaart.knopen[self.kaart.depot]
        self._tekst('Treindepot',depot['x']-24,depot['y']+9,5.8,vet=True)
        locaties={'FERRIS':(205,4),'ARCADE':(183,89),'WILDWATER':(177,135),
                  'FREEFALL':(275,135),'COASTER':(373,130)}
        for aid,a in self.kaart.attracties.items():
            k=self.kaart.knopen[a['doelknoop']];x,y=k['x'],k['y']
            item=s.addEllipse(x-4.5,y-4.5,9,9,pen('#ffffff',1),QBrush(QColor('#7d8fa3')))
            item.setZValue(3);self.stations[aid]=item
            badge=self._tekst('',x-2,y-4,5,'#ffffff',True)
            badge.setZValue(5);self.badges[aid]=badge
            lx,ly=locaties.get(aid,(x+8,y-8))
            self._tekst(a['naam'],lx,ly,5.5,vet=True)
        # Een compacte vector-shuttle met neus naar rechts.
        p=QPainterPath();p.moveTo(-6,-3.8);p.lineTo(3,-3.8)
        p.lineTo(7,0);p.lineTo(3,3.8);p.lineTo(-6,3.8);p.closeSubpath()
        self.shuttle=QGraphicsPathItem(p)
        self.shuttle.setPen(pen('#ffffff',1.1));self.shuttle.setBrush(QColor(NAVY))
        self.shuttle.setZValue(10);s.addItem(self.shuttle)
        self.shuttle.setPos(depot['x'],depot['y'])
        bounds=s.itemsBoundingRect().adjusted(-18,-20,18,20)
        # Ook Bezier-controlepunten bepalen de ruimte voor de buitenbocht.
        for e in self.kaart.verbindingen.values():
            for x,y in e['geometrie']['points']:
                bounds=bounds.united(QRectF(x-12,y-12,24,24))
        s.setSceneRect(bounds)

    def passend(self):
        self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.passend()

    def wheelEvent(self,event):
        factor=1.15 if event.angleDelta().y()>0 else 1/1.15
        huidige=self.transform().m11()
        if .5 < huidige*factor < 15: self.scale(factor,factor)
        event.accept()

    def toon_ids(self,aan):
        for item in self.ids.values(): item.setVisible(aan)

    def ververs(self,beeld):
        plan=beeld['plan'];index=beeld['stapindex']
        bezocht=tuple(beeld['status']['bezocht']) if not beeld['voorbeeld'] else ()
        toekomst=set();verleden=set()
        if plan:
            for i,stap in enumerate(plan['stappen']):
                if 'via' in stap:
                    (verleden if i<index else toekomst).add(stap['via'])
        kleuren=(frozenset(toekomst),frozenset(verleden),beeld['edge'],bezocht,beeld['service'],
                 tuple(plan['bestemmingen']) if plan else ())
        if kleuren!=self._laatste_kleuren:
            self._laatste_kleuren=kleuren
            for eid,item in self.wegen.items():
                kleur,breedte='#cbd4df',5
                if eid in verleden: kleur='#9ccfc0'
                if eid in toekomst: kleur=TEAL
                if eid==beeld['edge']: kleur,breedte=ORANGE,5.8
                item.setPen(pen(kleur,breedte))
            doelen=plan['bestemmingen'] if plan else []
            for aid,item in self.stations.items():
                kleur=GREEN if aid in bezocht else ORANGE if aid==beeld['service'] else TEAL if aid in doelen else '#7d8fa3'
                item.setBrush(QColor(kleur))
                k=self.kaart.knopen[self.kaart.attracties[aid]['doelknoop']]
                r=7 if aid==beeld['service'] else 4.5
                item.setRect(k['x']-r,k['y']-r,2*r,2*r)
                tekst='✓' if aid in bezocht else str(doelen.index(aid)+1) if aid in doelen else ''
                self.badges[aid].setText(tekst)
        self.shuttle.setPos(beeld['x'],beeld['y'])
        self.shuttle.setRotation(beeld['hoek'])
        self.shuttle.setBrush(QColor(ORANGE if beeld['status']['toestand']=='ZOEKEN' else NAVY))
