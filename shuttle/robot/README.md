# De werkelijke robotbesturing

Deze map is voor de ESP32. De gedeelde kaart en planner blijven in `gedeeld/`.
Alle modules kunnen voor softwaretests op de PC worden geimporteerd. Alleen
`hardware.initialiseer()` importeert `machine` en maakt GPIO/PWM-objecten.

## Wat nu is ingevuld

| Bestand | Verantwoordelijkheid |
|---|---|
| `config.py` | Pinnen, afstelling, WiFi, MQTT en expliciete startvoorwaarden |
| `hardware.py` | Vijf sensoren normaliseren, motorpolariteit en PWM |
| `lijnvolger.py` | Tijdgebaseerde PID, lijnpatronen en draaicommando's |
| `kruispunt_detector.py` | Bevestigen en vrijgeven van een passage, geen kaart-ID raden |
| `rit_besturing.py` | Volledige toestand, stappen, services, wijzigingen en eindcontrole |
| `robot_mqtt.py` | MQTT 3.1.1 TCP, begrensde inbox/ACK, duplicaten en sessies |
| `objectdetectie.py` | Toekomstige afstandsmeting met hysterese; momenteel expliciet uit |
| `main.py` | Hoofdloop, opstarten en altijd motoren uitschakelen bij afsluiten |
| `start_esp32.py` | Klein startbestand om als `/main.py` op de ESP32 te zetten |

## Wat je eerst moet invullen voor echt rijden

De code start nog niet automatisch met de huidige logische kaart. Dit is een
bewuste aansluiting op `RoutePlanner.plan(..., voor_robot=True)`.

1. Controleer bordvariant, pinnen, motorpolariteit en sensorvolgorde. De
   ingevulde nummers komen uit jullie eerdere main.py; ze zijn niet op ieder
   willekeurig ESP32-bord bruikbaar. Zet daarna `HARDWARE_BEVESTIGD = True`.
2. Leg de echte serviceplaatsen, aankomst-/vertrekedges en herkenningsmethode
   vast in `data/parcours.json`. De logische S-eindpunten zijn niet automatisch
   de T-haltes van de oude firmware. Stel versie/profiel en validatie pas na
   baancontrole bij. De depot-/startmethode moet ook gevalideerd zijn.
3. Herkenningsnamen: `rechtertak`, `linkertak`, `t_splitsing`, `zwart_blok`,
   `anker`. Een anker vereist dat echte extra hardware `meting['anker']` met
   een unieke knoop-ID levert; de gewone vijf lijnsensoren doen dat niet.
   `t_splitsing` bevestigt beide zijtakken en daarna geen doorgaande lijn.
   `zwart_blok` vraagt ononderbroken vijf zwarte bits gedurende `marker_ms`.
   Depot ondersteunt alleen de laatste twee methoden of een uniek anker.
   Ook ongevraagde eindpunten die de planner als keerplaats gebruikt moeten
   herkenbaar zijn. Als een oude S-stub na verplaatsen van een halte naar J
   geen herkenbaar eindpunt meer heeft, sluit die edge in de robotkaart met
   `actief: false`. Een plan met een onherkenbaar eindpunt wordt afgewezen.
4. Zet de robot fysiek in D00 in de afgesproken startrichting. Pas dan
   `STARTPOSITIE_BEVESTIGD = True`. Na handmatig stoppen/onzekerheid opnieuw
   naar het depot brengen en via `bevestig_start()` of een gecontroleerde
   herstart de startplaats bevestigen; er is geen automatische herlokalisatie.
5. Vul voor MQTT WiFi en `MQTT['broker']`, poort en eventuele credentials in.
   Standaard is de broker None en vindt geen netwerkverbinding plaats.
   Objectdetectie staat uit omdat er geen sensor aangesloten is. Inschakelen
   vereist een snelle meter of `afstand_mm` in de meting. Ontbrekende/verouderde
   afstandsmetingen blokkeren als detectie ingeschakeld is.
6. Kies lokale bestemmingen in `LOKALE_BESTEMMINGEN` of stuur een MQTT-opdracht.
   Een lokale rit gebruikt hetzelfde opdrachtenpad; standaard is de lijst leeg.

## Uitvoering en posities

Een vertrek-/keuze-/hoek-/keerstap kiest de uitgang van de `van`-knoop. Na
een stabiele gewone uitgaande lijn wordt de rijstap afgerond; de robot bevindt
zich dan op een edge. Pas de volgende passende passage bevestigt aankomst
volgens de routecontext. Een getelde passage is geen unieke plaatsmeting.

Er is geen opzettelijke meetstop bij een rechtdoor-passage. Een echte bocht
gebruikt de draaisturing. Wachten is een toestand van 5000 ms actieve tijd,
geen `sleep(5)`. Obstakelblokkering bevriest bewegings- en haltetimers; na
vrijgave hervat dezelfde onafgeronde actie. Expliciete STOP blijft gestopt.

Zoeken en draaien hebben geen maximale zoektijd. Lang lijnverlies maakt de
positie onzeker; de robot blijft zoeken, maar verbruikt geen routestap en
meldt geen fictieve aankomst. Na onzekerheid is gecontroleerde bevestiging
bij het depot nodig. Gewoon ergens een lijn terugvinden bewijst de plaats niet.

Nieuwe doelen onderweg vervangen de nog resterende doelen. Reeds bezochte
doelen worden geweigerd; een lopende service wordt eerst afgerond. Daarna
blijft `na_service` het fysieke servicevertrek afdwingen. Een opdracht tijdens
een bocht wacht tot de volgende geschikte knoop VOOR de uitgang gekozen is.
Een onuitvoerbare wijziging wordt afgewezen en laat het lopende plan intact.

## MQTT-contract

Deze eerste versie gebruikt MQTT 3.1.1 over gewone TCP, zonder TLS. Gebruik
hiervoor jullie afgesproken school-/lokale broker. Verbindingsinstellingen en
wachtwoorden niet publiek committen. TLS/andere brokerauthenticatie is een
aparte volgende stap als jullie broker die vereist.

Topics voor robot01:

- `school/shuttle/robot01/command`: niet retained; QoS 0 met applicatie-ACK/retry.
- `school/shuttle/robot01/ack`: `accepted`, `pending`, `applied`, `rejected`, `duplicate`.
- `school/shuttle/robot01/status`: retained laatste toestand, inclusief boot-sessie.

```json
{
  "command_id": "cmd-001", "command_seq": 1,
  "robot_id": "robot01", "sessie_id": "waarde-uit-huidige-status",
  "actie": "start", "mission_id": "rit-001", "revisie": 1,
  "kaartversie": "jullie-gevalideerde-kaartversie",
  "bestemmingen": ["WILDWATER", "FREEFALL"]
}
```

`vervang` houdt dezelfde mission_id en heeft een revisie hoger dan de actieve
EN wachtende revisie. Elke nieuwe opdracht heeft een hogere command_seq en
nieuwe command_id; een retry houdt de volledige inhoud en ID gelijk. `stop`
heeft alleen de envelope (ID/seq/robot/sessie/actie) nodig. Ontvangst/acceptatie
betekent niet dat de rit succesvol is. Alleen eindstatus `resultaat=succesvol`
na alle services plus depotbevestiging geldt als afgeronde rit.

Er worden maximaal 32 geaccepteerde opdrachten onthouden. Oudere seq-nummers
worden ook na verdwijnen uit die cache geweigerd. Inbox is 8 en ACK-wachtrij
16; bij teveel verkeer moet de afzender dezelfde ID opnieuw proberen. Laatste
status en laatste ritresultaat blijven beschikbaar in RAM; na stroomreset
komt een nieuwe sessie en wordt niet blind hervat. Dit is geen permanente log.

TCP lezen/schrijven en MQTT-framing gebeuren in korte updates, inclusief
gefragmenteerde pakketten. DNS/TCP verbinden gebeurt uitsluitend als motoren
stil staan: opstarten, halte of blokkering. Bij netwerkverlies blijft een
lokaal geldige rit mogelijk; opnieuw verbinden wordt uitgesteld tot stilstand.
Er is geen gemeten garantie van een 5ms-cyclus op jullie ESP32.

Voor tests en latere simulatie: `RobotMqtt(..., bron='simulatie')` en
`RitBesturing(..., voor_robot=False)`. Simulatietopics en robot-ID krijgen een
aparte naam. Alleen die modus accepteert expliciete knoopwaarnemingen via
`verwerk_waarneming()`. De echte robot gebruikt ruwe metingen via `update()`.

## Uploaden en testen

Op de ESP32 moet deze indeling staan:

```text
/main.py           <- inhoud van robot/start_esp32.py
/robot/*.py        <- inclusief __init__.py, config.py en main.py
/gedeeld/*.py      <- inclusief __init__.py
/data/parcours.json
```

`robot/main.py` alleen als root-main.py uploaden werkt niet met de relatieve
imports. Het kleine startbestand importeert juist `robot.main.main`.
Op de computer voer je de tests uit, vanuit shuttle:

```powershell
python -m unittest discover -s tests -v
```

De tests bevatten nagebootste sensoren/ankers, PWM en TCP-fragmenten. Ook alle
325 bezoekvolgorden worden door de uitvoerder doorlopen. Dat bewijst geen
fysieke rijprestatie of verbinding met jullie nog niet ingevulde broker.

Technische bronnen: MicroPython PWM en ticks-tijd, en MQTT 3.1.1:
- https://docs.micropython.org/en/latest/library/machine.PWM.html
- https://docs.micropython.org/en/latest/library/time.html
- https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
