# Grafische parcoursweergave met PyQt6

Start vanuit de map shuttle met `python -m simulatie`. Met de meegeleverde
virtuele omgeving: `.\.venv\Scripts\python.exe -m simulatie`. Op Windows kun
je ook dubbelklikken op `Start_simulatie.bat`; die gebruikt de .venv indien aanwezig.

Eenmalig installeren, met Python 3.10 of nieuwer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sim.txt
```

De simulator vindt data/parcours.json op basis van zijn eigen locatie. Het
venster toont de echte polyline-/Bezier-geometrie uit dat bestand. De
schematische coordinaten zijn geen afstanden in meters.

## Bediening

1. Kies een attractie en voeg die met + toe. Verander de bezoekvolgorde met
   Omhoog/Omlaag. De standaardproef is Wildwaterbaan, Vrijevaltoren, depot.
2. Route bekijken toont het plan. Start rit voert hetzelfde plan uit via de
   bestaande RitBesturing, met logische simulatiewaarnemingen.
3. Teal is de resterende route, oranje de actieve verbinding/halte, groen een
   bezocht doel. De shuttle beweegt over de getekende lijnen en bochten.
4. Pauze bevriest de simulatietijd. Stap +0,1 s werkt tijdens pauze. Snelheid
   1x/2x/5x/10x versnelt de hele simulatietijd, ook de vijf seconden halte.
5. Wijzig resterende route stuurt een normale vervang-opdracht door de
   simulatie-MQTT-envelope. Zij wordt pas op een geschikte knoop toegepast.
   Een lopend bezoek wordt eerst afgerond. De lijst toont nog te bezoeken
   attracties; reeds bediende doelen en de lopende halte worden eruit gehaald.
6. Obstakel blokkeert de motoractie en bevriest de actieve haltetijd. Haal het
   vinkje weg om dezelfde actie te hervatten.
7. Lijn kwijt injecteert witte sensormetingen. Langdurig verlies maakt de
   plaatsinschatting onzeker: de besturing blijft zoeken en meldt geen succes.
   Gebruik Reset naar depot om daarna een nieuwe gecontroleerde proef te doen.
8. Stop beeindigt de uitvoering; Reset naar depot zet de proef terug naar de
   uitgangssituatie. Bij succesvolle terugkeer kun je ook direct nieuwe doelen
   toevoegen en een tweede rit starten.
9. Puntnummers zijn optioneel. Scroll op de kaart om te zoomen; sleep om te
   schuiven. Passend maken toont weer de hele kaart.

Rechts kun je omlaag scrollen voor alle geplande ritstappen. Ritverloop toont
bezoeken, wachten, wijzigingen en terugkeer in gewone tekst in plaats van JSON.

## Hoe dit met de bestaande code samenwerkt

- `simulator.py`: kleine adapter die ParcoursKaart, RoutePlanner, RobotMqtt en
  RitBesturing samenstelt met bron='simulatie' en voor_robot=False.
- `geometrie.py`: punten langs rechte en ronde verbindingen, interpolatie en richting.
- `kaart_weergave.py`: tekent uitsluitend de kaart en de actuele toestand.
- `venster.py`: bediening met PyQt6-widgets en QTimer.
- `main.py` / `__main__.py`: starten van de desktopapp.

Er wordt geen echte GPIO geopend en er is geen netwerkverbinding. De
RobotMqtt-component verwerkt opdrachten lokaal met een aparte simulatie-ID;
de broker staat in deze adapter altijd op None. Als een kaartpunt grafisch
bereikt is, krijgt de besturing een expliciete simulatiewaarneming. De
bewegings- en haltetoestanden komen vervolgens uit dezelfde besturing als de
firmware. De vaste software-update is 5 ms; Qt tekent ongeveer elke 20 ms.

Deze simulatie bewijst routes en ritlogica, geen sensorbereik, tractie,
batterijgedrag of fysieke draaiprestatie. De geanimeerde rijsnelheid is 45
schetseenheden/s. De adapter gebruikt een klein aantal interne uitvoervelden
van RitBesturing om synthetische draaipatronen te leveren; de integratietests
bewaken die koppeling.

## Testen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`test_simulatie.py` test animatie, geometrie, pauze, wachten, tweede rit en
wijzigingen. `test_pyqt_venster.py` bedient de echte widgets in offscreen-modus.
Zonder PyQt6 worden alleen de venstertests overgeslagen. De bestaande kaart-,
MQTT- en robotbesturingstests blijven behouden.

Technische documentatie:
- https://pypi.org/project/PyQt6/6.12.0/
- https://doc.qt.io/qt-6/qgraphicsscene.html
- https://doc.qt.io/qt-6/qgraphicspathitem.html
- https://doc.qt.io/qt-6/qtimer.html
