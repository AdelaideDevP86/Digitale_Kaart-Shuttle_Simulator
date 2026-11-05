# Lijnherstel 5 november 2026

Deze update behoudt je huidige route `ARCADE`, de kaart, pinnen, basissnelheid
0.35, draaisnelheid 0.30, KP 0.75, KI 0 en KD 0.15. Hij verandert de uitvoering
en de D-berekening. De oude instelinstructies in TEST_MORGEN.md zijn op de
hieronder genoemde punten vervangen.

## Wat verandert

1. Tijdens zoeken: zodra een gewone lijn terugkomt, krijgen de motoren nul
   tijdens de bevestiging van 25 ms. Voorheen bleef hij tijdens die 25 ms op
   volle zoeksnelheid draaien. Na bevestiging hervat dezelfde edge/uitgang.
2. Ook in de ZWART-fase van een bocht geeft hij nul zodra de gewenste lijn
   onder het midden ligt, tijdens de bevestiging. De WIT-fase en bij keren
   de minimumtijd blijven voorkomen dat de oude lijn direct wordt geaccepteerd.
3. Een vastgestelde verkeerde routewaarneming stopt met fout. Hij draait niet
   meer acht seconden rond terwijl hervatten vanwege onzekerheid geblokkeerd is.
   Bij gewoon lijnverlies kan hij binnen 1800 ms herstellen. Daarna stopt hij
   met fout, ook als de ruimere zoek-timeout van 8000 ms nog niet bereikt is.
   Onzekerheid wordt nooit stilzwijgend veranderd in een bekende kaartpositie.
4. Keren: achteruit is opnieuw ingeschakeld, maximaal 800 ms en met snelheid
   0.35. Hij bevestigt de teruggevonden gewone lijn 25 ms voordat hij draait.
   Vindt hij die niet terug, dan stopt hij met een duidelijke fout in plaats
   van vanaf een onbekende plek blind rond te draaien. De minimumkeertijd
   700 ms telt vanaf het echte draaien, niet vanaf het achteruitrijden.
5. Na een geplande linker/rechterbocht onthoudt de zoeksturing die richting;
   hij gebruikt niet onbedoeld een oude richting van voor de bocht.
6. De D-term wordt bij een onvolledig tijdvenster begrensd: de eerste 5 ms
   kunnen de correctie niet meer tienmaal versterken ten opzichte van het
   bedoelde venster van 50 ms. De ingestelde KP/KI/KD blijven gelijk.
7. Een drie-bits zijpatroon op de laatste edge start geen depotkandidaat meer.
   Bij terugkeer blijven minstens vier zwarte sensoren de bestaande voorwaarde
   voor het depotblok. Dit moet 500 ms onafgebroken aanhouden. Hij staat daar
   tijdens bevestigen stil; onderbreking reset de timer en is niet op zichzelf
   een routefout. Een blok is alleen depotbewijs als de route D00 verwacht.
   De bestaande mogelijkheid om vanuit de laatste draai direct op het nabije
   depotblok uit te komen blijft behouden.

Er is geen nieuwe meetstop bij een normale rechtdoor-passage. Het kort nul
aansturen hierboven hoort bij het terugvinden van de lijn tijdens een draai
of zoekpoging. Of de echte motoren daarmee snel genoeg afremmen moet je op de
baan controleren. Draaipunt (uitlijnen_ms=120) en minimumkeertijd (700 ms) zijn
nog steeds fysieke afstelwaarden; de PC-tests meten die niet.

## Upload alleen deze vier gewijzigde robotbestanden

Open PowerShell in `C:\Users\noura\Documents\DigitalekaartShuttleSimulatie\shuttle`.
Sluit een andere seriele monitor. Gebruik de echte poort in plaats van COM5.
Zet tijdens de overdracht de wielen vrij van de grond.

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 cp robot/config.py :robot/config.py
.\.venv\Scripts\mpremote.exe connect COM5 cp robot/lijnvolger.py :robot/lijnvolger.py
.\.venv\Scripts\mpremote.exe connect COM5 cp robot/rit_besturing.py :robot/rit_besturing.py
.\.venv\Scripts\mpremote.exe connect COM5 cp robot/main.py :robot/main.py
```

De bestaande gedeeld/, data/parcours_robot.json, root-main.py, hardware.py en
rit_log.py blijven nodig. Deze vier commando's zijn een update van een eerder
volledig overgezet project, geen installatie op een leeg bord.

Zet de robot terug in D00, gericht naar de eerste aansluiting, en start:

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 reset repl
```

Controleer op `Besturing: LIJNHERSTEL_20261105_1` en `LOKALE ROUTE: ARCADE -> DEPOT`.
De lokale route begint na de ingestelde opstartwachttijd van 7 seconden.
Test eerst deze korte rit. Een fout is pas onderzocht met de nieuwe log:

```powershell
.\.venv\Scripts\mpremote.exe connect COM5 cp :ritlog.jsonl ritlog_na_lijnherstel.jsonl
```

In de log is `lijn_vastpakken` het moment waarop hij een teruggevonden lijn
bevestigt. Bij een echte fout staat de reden in de laatste `stop`-gebeurtenis.
Verander eerst geen andere afstelwaarden: dan kun je deze uitvoering apart
vergelijken met de vorige proef.

## Softwarecontrole

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De proeven omvatten de planner, alle 325 unieke bestemmingsvolgorden, de
besturing, MQTT, GUI en sensorreeksen. Nieuwe regressies controleren remmen
op de gevonden lijn, hervatten zonder extra routestap, stoppen bij onzekerheid,
depotruis, onderbroken blokbevestiging en de D-opstartsprong. Dit is geen
garantie dat de mechanische afstelling op de echte robot klopt.
