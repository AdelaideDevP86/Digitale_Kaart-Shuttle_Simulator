# Gedeelde modules - vast contract, versie 1

Deze twee modules vormen de basis voor de latere simulator, RitBesturing en MQTT.
Ze importeren geen `machine`, grafische pakketten of netwerkbibliotheken.
De besturing blijft verantwoordelijk voor werkelijk meten, rijden en aankomst
bevestigen. Een berekende stap is nooit een gemeten positie.

## Bestanden en imports

```python
from gedeeld import ParcoursKaart, RoutePlanner

kaart = ParcoursKaart.uit_bestand("data/parcours.json")
planner = RoutePlanner(kaart)
positie = {
    "laatste_punt": "D00",
    "in_edge": None,
    "op_knoop": True,
    "status": "start_bevestigd",
}
plan = planner.plan(positie, ["WILDWATER", "FREEFALL"])
```

Start scripts vanuit de map `shuttle`. `data/parcours.json` is de centrale
kaart voor de simulator en de gedeelde planner. Lees `data/README.md` voor
de velden, tekengeometrie en de nog te valideren fysieke halteplaatsen.
`tests/fixtures/parcours_logisch.json` blijft een zelfstandige regressiekaart.
Beide gebruiken voorlopig het logische profiel, geen goedgekeurde robotconfiguratie.

## JSON-kaart

Verplichte topvelden: `versie` (niet-lege string), `depot`, `start_edge`, `knopen`,
`verbindingen`, `attracties`. De laatste drie zijn lijsten met unieke `id`-velden.
`profiel` is `logisch` (standaard) of `robot`.

- Knoop: `id`, `soort` (`depot`, `keuze`, `hoek`, `eindpunt`), `poorten` (bijv. `NSE`).
- Verbinding: `id`, `a`, `a_poort`, `b`, `b_poort`; optioneel `actief` (bool, standaard True).
- Attractie: `id`, `doelknoop`, `aankomst_edge`, `vertrek_edge`.
  Optioneel `naam`, `herkenning` (string), `gevalideerd` (bool, standaard False).
- Voor een echt robotprofiel: `depot_herkenning` met `methode` (string) en
  `gevalideerd: true`. Deze vlaggen mogen pas na fysieke controle worden gezet.
- Extra tekenvelden zoals `x`, `y`, `vorm` en `geometrie` mogen blijven staan.

Alle verbindingen zijn tweerichtingsverkeer. Een poort wijst vanuit de knoop
naar buiten. De poorten aan beide uiteinden hoeven geen tegenpolen te zijn:
een ronde verbinding kan onderweg van richting veranderen.

Elke gedeclareerde poort wordt precies eenmaal aangesloten. De basisgraaf moet
verbonden zijn, ook als er tijdelijk wegen gesloten zijn. Afsluitingen via
`actief: false` of `kaart.blokkeer(edge_id)` kunnen een doel onbereikbaar maken;
de planner geeft dan `ValueError`. `deblokkeer` heft alleen de tijdelijke
blokkade op, niet een vaste `actief: false`-instelling.

Elk serviceprofiel heeft in deze eerste versie precies een aankomst-/vertrekpaar.
Een doelknoop wijzigen van een eindpunt naar een T-splitsing is onvoldoende:
pas ook beide edges aan. Een gewone passage langs een attractie is geen service.
Een expliciete serviceovergang mag keren op de serviceknoop; een gewone route
mag alleen keren bij depot of eindpunt. De planner dwingt na service altijd de
vaste vertrekedge af. Hij bedenkt zelf geen andere fysieke vertrekbeweging.

## Positie op een routegrens

`plan()` krijgt `laatste_punt`, `in_edge`, `op_knoop: True` en een status uit
`start_bevestigd`, `depot_bevestigd`, `route_aannemelijk`. Inkomende edge mag
alleen `None` zijn voor de bekende start in het depot. Onderweg op een
verbinding: `op_knoop: False`; daar wordt een nieuwe route geweigerd. Bij
onzekere positie wordt eveneens geweigerd.

Na een afgeronde halte, **voor vertrek**, geeft RitBesturing bovendien
`na_service: "WILDWATER"` (of ander attractie-ID) mee. Dan blijft de verplichte
vertrekedge gelden bij een routewijziging. Bij de eerstvolgende rijstap vervalt
die marker in de echte besturing. Een normale passage krijgt deze marker niet.

`pad(start, in_edge, doel, doel_in=None)` is een lagere hulpmethode en retourneert
uitsluitend rijstappen. Zij verricht geen services en kijkt niet zelf of er een
robot op de lijn staat. Gebruik `plan` vanuit RitBesturing.

## Planformaat

`plan(positie, bestemmingen, voor_robot=False)` retourneert een dictionary met:

- `schema_versie: 1`, `kaartversie`, `voor_robot`, `start`, `bestemmingen`, `stappen`.
- Rijstap: `index`, `soort` (`vertrek`, `keuze`, `hoek`, `keren`), `van`, `via`,
  `naar`, `actie` (`vertrek`, `links`, `rechts`, `rechtdoor`, `keren`).
  `servicevertrek` is het attractie-ID bij een verplichte vertrekstap, anders `None`.
- Servicestap: `index`, `soort: "service"`, `doel`, `knoop`, `aankomst_edge`,
  `vertrek_edge`, `wacht_ms: 5000`. Geen motorcommando of blokkerende slaap.
- Laatste stap: `index`, `soort: "einde"`, `knoop` (het depot).

Bestemmingen: een lijst van 1 t/m 5 unieke bekende attractie-IDs. De volgorde
blijft behouden. De planner voegt zelf terugkeer naar het depot toe.
`voor_robot=True` vereist een gevalideerd robotprofiel; default is logische
planning. RitBesturing moet de robotoptie gebruiken voor echte motorbesturing.

BFS zoekt over `(knoop, inkomende verbinding)`; alle verbindingen hebben kost 1.
Een pad is minimaal in aantal verbindingen binnen de vastgelegde aanrit- en
vertrekregels. Dat is geen claim over minimale meters of reistijd. Dezelfde
invoer en kaart geven steeds hetzelfde plan. Maximaal 5 attracties en kleine
graaf: geen externe routebibliotheek of extra klassen nodig.

`valideer_plan(plan)` retourneert `[]` bij een geldig volledig plan, anders een
lijst foutmeldingen. Gebruik deze controle opnieuw voordat een plan geinstalleerd
wordt: een verbinding kan intussen geblokkeerd zijn. Extra MQTT-metadata mag
later naast de planvelden worden bijgehouden.

## Testen op de computer

Vanuit `shuttle`:

```powershell
python -m unittest discover -s tests -p test_kaart_planner.py -v
```

De testkaart gebruikt getekende eindpunten als attractiedoelen. De testen op de
computer bewijzen de kaart- en plannerlogica. Ze bewijzen geen sensorherkenning,
PWM-afstelling of fysieke terugkeer naar het depot. Er is nog niet getest op de
ESP32; daarvoor moet ook de werkelijk gebruikte MicroPython-versie bekend zijn.
