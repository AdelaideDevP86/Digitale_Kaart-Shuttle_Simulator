# De digitale parcourskaart

`parcours.json` is de centrale kaart voor de simulator en `ParcoursKaart`.
Er staat geen vaste rit in. De planner kan er verschillende bezoekvolgorden uit
berekenen, inclusief terugkeer naar het depot.

De kaart bevat 27 punten, 32 tweerichtingsverbindingen en vijf attracties. Alle
IDs en verbindingen volgen het kaartmodel uit de ontwerp-PDF en de bronfoto.

## Inladen

Start vanuit de map `shuttle`:

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
for stap in plan["stappen"]:
    print(stap)
```

`RoutePlanner` voegt vijf seconden service per gevraagd bezoek en de terugweg
naar het depot toe. Die acties staan in het berekende plan, niet in de kaart.
Bestemmingen komen later uit de bediening of MQTT. De vaste attractie-IDs zijn:

| ID voor opdrachten | Attractie | Logisch doel | Aankomst-/vertrekedge |
|---|---|---|---|
| `FERRIS` | Reuzenrad | S01 | E18 |
| `ARCADE` | Arcadehal | S02 | E32 |
| `WILDWATER` | Wildwaterbaan | S03 | E28 |
| `FREEFALL` | Vrijevaltoren | S04 | E24 |
| `COASTER` | Achtbaan | S05 | E21 |

De namen voor mensen mogen anders zijn; de IDs blijven hetzelfde in kaart,
MQTT, simulator en besturing.

## Betekenis van de velden

- `versie`: nu `foto-v1-logisch`. Wijzig de versie wanneer aansluitingen,
  poorten, serviceplaatsen of aankomst-/vertrekregels veranderen.
- `profiel`: nu `logisch`. `voor_robot=True` wordt hiermee geweigerd.
- `depot`: D00; `start_edge`: E01, vanuit depot naar J01.
- `depot_herkenning`: fysieke herkenningsmethode en validatiestatus; nog niet ingevuld.
- `knopen`: punten met ID, naam, soort, poorten en schetscoordinaten.
- `verbindingen`: aansluitingen met hun lokale eindpoorten, actief-vlag en tekengeometrie.
- `attracties`: koppeling tussen opdracht-ID, doelknoop en serviceprofiel.
- `metadata`: herkomst en betekenis van de coordinaten; geen kalibratiegegevens.

Soorten knopen:

| Soort | ID's | Betekenis |
|---|---|---|
| `depot` | D00 | Treindepot |
| `keuze` | J01 t/m J16 | Kruispunt waar meerdere uitgangen bestaan |
| `hoek` | C01 t/m C05 | Verplichte hoek, geen vrije afslagkeuze |
| `eindpunt` | S01 t/m S05 | Getekend lijneinde bij een attractie |

Poorten N/E/S/W wijzen **vanuit de knoop naar buiten** op de tekening. Bij een
verbinding worden beide eindpoorten apart vastgelegd. E19, de buitenbocht,
sluit bijvoorbeeld aan beide kanten via N aan. Reken de afslag dus uit met de
poorten, niet met een rechte lijn tussen de coordinaten.

## Tekenen van de kaart

`x` groeit naar rechts en `y` naar beneden. Het zijn schematische eenheden,
geen gemeten afstanden. Maak de weergave passend door alle punten en
controlepunten mee te nemen in het zichtbare bereik; enkele controlepunten
van de buitenbocht hebben een negatieve y-waarde.

Een verbinding heeft `vorm` als leesbaar label en `geometrie` voor tekenen:

- `kind: "polyline"`: verbind de lijst `points` achtereenvolgens.
- `kind: "cubic_bezier"`: vier punten, begin P0, controlepunten P1/P2 en eind P3.
  Voor 0 <= t <= 1 geldt:
  `B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t)t^2 P2 + t^3 P3`.

De eerste en laatste punten moeten overeenkomen met de gekoppelde knopen.
De planner gebruikt de aansluitingen en poorten; deze tekenvorm bepaalt geen
motorsnelheid of fysieke rijtijd.

## Tijdelijk een weg afsluiten

```python
kaart.blokkeer("E28")
# Nieuwe planning meldt nu dat Wildwaterbaan niet bereikbaar is.
kaart.deblokkeer("E28")
```

`actief: false` in de JSON is een vaste afsluiting. `deblokkeer()` verwijdert
alleen een tijdelijke blokkade. Controleer bestaande plannen na een afsluiting
opnieuw met `planner.valideer_plan(plan)`.

## De echte halteplaatsen nog vastleggen

In het logische profiel rijdt de getekende robot naar het eindpunt S01-S05 en
keert daar via dezelfde edge. Dat is een afspraak voor de eerste simulatie.
De bestaande echte robot kan juist bij een aansluiting stoppen en via een
andere tak vertrekken. De aansluitingen bij de attracties zijn:

| Attractie | Aansluiting die fysiek onderzocht moet worden |
|---|---|
| Reuzenrad | J16 |
| Arcadehal | J12 |
| Wildwaterbaan | J13 |
| Vrijevaltoren | J14 |
| Achtbaan | J15 |

Voorbeeld van een alternatief **onbevestigd** Wildwaterprofiel: doel J13,
aankomst E27 en vertrek E26. Daarmee vertrekt hij rechts via het zijpad, in
plaats van automatisch te keren op S03. Dit staat niet als fysieke waarheid in
de centrale kaart: eerst op de baan aankomst, vertrek en herkenning controleren.

Vul daarna per attractie `doelknoop`, `aankomst_edge`, `vertrek_edge`,
`herkenning` en `gevalideerd` correct in. Leg ook de depot-/startmethode vast,
pas profiel/kaartversie aan en voer de route- en fysieke tests opnieuw uit.
Alleen de vlaggen op true zetten is geen validatie. Zie `../GEDEELD_API.md`
voor de afspraken over posities, servicevertrek en robotplannen.

## Tests

```powershell
python -m unittest discover -s tests -v
```

`test_parcours_data.py` controleert het echte centrale databestand, waaronder
tekengeometrie, alle 325 geordende attractieselecties en richtingbewuste routes.
De eerdere testfixture blijft apart staan om de gedeelde modules ook met een
vaste regressiekaart te testen.
