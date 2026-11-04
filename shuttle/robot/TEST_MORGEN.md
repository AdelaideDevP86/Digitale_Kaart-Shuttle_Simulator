# Campusproef: Wildwaterbaan -> Vrijevaltoren -> depot

## Wat is ingesteld

- `config.KAARTPAD` gebruikt `data/parcours_robot.json`.
- Lokale rit: `WILDWATER`, `FREEFALL`, daarna automatisch depot.
- Wildwater blijft S03, via E28. Vrijeval blijft S04, via E24.
  J13 en J14 blijven kruispunten; daar wordt geen service uitgevoerd.
- Beide attracties: alle vijf sensoren wit gedurende 60 ms op de
  verwachte laatste edge betekent lijneinde. Daar 5000 ms wachten en keren.
- Depot D00: vijf zwarte bits gedurende 500 ms. Tijdens die bevestiging
  houdt hij op het blok stil; hij kan het blok daardoor niet voorbijrijden.
- De andere drie attracties zijn nog niet als robotdoel geconfigureerd.
  Een opdracht daarvoor wordt geweigerd. De simulator gebruikt de oorspronkelijke
  logische `data/parcours.json` en kan wel alle vijf attracties gebruiken.
- `HARDWARE_BEVESTIGD` en `STARTPOSITIE_BEVESTIGD` staan voor deze lokale proef
  op True. Dit zijn aannames, geen automatische metingen: gebruik de bestaande
  robot met deze pinnen en zet hem voor IEDERE reset in D00 richting J01.
- Objectdetectie en netwerk blijven uit zolang jullie die niet invullen.

Dit is een geconfigureerd testprofiel op basis van de opgegeven lijneinden en
het depotblok. Motorfysica, draaipunt en herkenningstijden zijn niet op jullie
robot gemeten. Een scheur of onderbreking langer dan 60 ms op een verwachte
laatste edge kan met alleen vijf lijnsensoren ook op een lijneinde lijken.

## Bestanden overzetten

Open een PowerShell-terminal in de projectmap `shuttle`. Sluit andere seriele
monitoren die de ESP32-poort bezet houden. Als mpremote nog ontbreekt:

```powershell
.\.venv\Scripts\python.exe -m pip install mpremote
.\.venv\Scripts\mpremote.exe connect list
```

Vervang hieronder COM5 door de werkelijke poort. Zet voor de overdracht de
wielen vrij van de grond. Hieronder staat de complete package-overdracht;
alleen het oude root-main.py vervangen is onvoldoende.

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 cp -r gedeeld/ :
.\.venv\Scripts\mpremote.exe connect COM5 cp -r robot/ :
.\.venv\Scripts\mpremote.exe connect COM5 fs mkdir :data
.\.venv\Scripts\mpremote.exe connect COM5 cp data/parcours_robot.json :data/parcours_robot.json
.\.venv\Scripts\mpremote.exe connect COM5 cp robot/start_esp32.py :main.py
```

Als `data` al bestaat, sla `mkdir` over. De package `robot/` moet ook de nieuwe
`rit_log.py` bevatten. De .venv, simulatie en PC-tests hoeven niet op het bord.
`mpremote cp` installeert geen MicroPython-firmware; die moet al op het bord staan.

Zet de robot in het depot en start met de seriele uitvoer zichtbaar:

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 reset repl
```

Er moet `LOKALE ROUTE: WILDWATER -> FREEFALL -> DEPOT` verschijnen, plus
kaartversie `foto-v2-robot-lijneinden-20261104`. Verschijnt die versie niet,
dan draait een ouder bestand of verwijst config naar de verkeerde kaart.
De lokale rit start na opstarten automatisch; een reset begint weer bij D00.

## Afstelling op de baan

1. Houd de wielen eerst vrij en schuif lijn en wit onder de sensoren:
   het patroon heeft vijf bits, van links naar rechts, met 1 voor zwart.
   Controleer tegelijk dat twee positieve motorwaarden echt vooruit betekenen.
2. Rijd een korte proef. Basis-, draai- en zoeksnelheid staan op 0.35.
   PID blijft KP 0.60, KI 0, KD 0.15. PID verandert geen kruispunttelling.
3. `uitlijnen_ms=120` is de rechte aanloop VOOR een links/rechts-bocht.
   Draait hij te vroeg, verhoog met kleine stappen; te laat, verlaag.
   Begin in het gebied 100-200 ms, maar meet op jullie robot.
   Bij keren aan het lijneinde wordt deze voorwaartse aanloop overgeslagen.
4. `keer_min_ms=700` is de bestaande minimumtijd voor keren. Als de correcte
   teruggaande lijn al eerder wordt gepasseerd, moet deze tijd lager worden
   afgesteld. Controleer een enkele halve draai voordat je de hele rit test.
5. Meet een echt lijneinde: `lijneinde_ms=60` onderscheidt kort wit van een halte.
   Te kort kan een onderbreking als halte tellen; te lang laat hem verder
   voorbij het lijneinde rollen. Het chassis staat achter de sensorbalk.
6. Controleer daarna beide haltes en de terugkomst op het depotblok.
   Test ook de accutoestand die je tijdens de demonstratie gebruikt.

Bij een rechtdoor-passage is er geen extra meetstop. Een buitenste sensor moet
10 ms zichtbaar zijn om een zijtak te bevestigen. Ontbreekt de geplande tak
nog, dan blijft hij maximaal 250 ms op basissnelheid aanvullende metingen
verzamelen; hij telt in die periode geen tweede kruispunt. Een blijvende
afwijking veroorzaakt positie-onzekerheid, geen verzonnen afslag.

## Als het fout gaat

- Gewoon lijnverlies: tot 1800 ms kan een stabiel teruggevonden lijn de rit
  hervatten, met dezelfde edge en stap. Daarna is de positie onzeker.
- Een zoekpoging stopt na 8000 ms met `toestand=GESTOPT`, `resultaat=fout`.
- Een onafgeronde draai/uitgang stopt na 6000 ms met hetzelfde foutresultaat.
- Een obstakel bevriest deze actieve timers, evenals de haltewachttijd.
- Na een fout niet midden op de baan opnieuw starten: terug naar D00.
- `succesvol` verschijnt alleen na beide bezoeken en bevestiging van D00.

De laatste sensormetingen en gebeurtenissen blijven tijdens rijden in RAM.
Na KLAAR/GESTOPT (of afsluiten) schrijft main `ritlog.jsonl` naar het bord.
De twee begrensde buffers bewaren maximaal 128 events en 160 metingen.
Een stroomonderbreking kan een nog niet opgeslagen RAM-log verliezen.
Haal de log op terwijl de robot stilstaat:

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 cp :ritlog.jsonl ritlog_robot.jsonl
```

Noteer bij een fout de laatste fysieke plek en de laatste seriele melding.
In de log staan o.a. `uitgang`, `passage`, `punt_bevestigd`, `aankomst`,
`service_klaar`, `zoeken`, `stop`, het patroon en de verwachte knoop.

## PC-controle

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`tests/test_robot_baan.py` voert de volledige heen-/tussen-/terugrit uit met
synthetische sensorpatronen in fysieke besturingsmodus, plus ruis, laat zichtbare
zijtakken, korte lijnonderbrekingen, timeouts en RAM-log. Dat bewijst de
beslislogica, niet dat de gemeten afstanden en tijden op de baan kloppen.
