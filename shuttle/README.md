# Digitale kaart en shuttle-simulatie

PyQt6-desktopapp voor het parcours met vijf attracties en een treindepot.
De grafische weergave gebruikt dezelfde kaart, routeplanner en ritbesturing
als de gedeelde/robotmodules. De simulatie opent geen echte motoren of MQTT-broker.

## Starten op Windows

Vanuit de map shuttle, eenmalig:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sim.txt
```

Daarna dubbelklikken op **Start_simulatie.bat** of:

```powershell
.\.venv\Scripts\python.exe -m simulatie
```

Kies de attracties, klik Start rit en volg de shuttle op de kaart. Met Pauze,
Stap, de afspeelsnelheid, routewijzigingen, obstakel en lijnverlies kun je
verschillende scenario's visueel uitproberen. De kaartnummers en de gewone
tekst bij Ritverloop helpen bij het bespreken van een afwijkende route.

## Indeling

- `data/`: de centrale kaart; voorlopig logisch profiel.
- `gedeeld/`: kaartvalidatie en richtingbewuste routeplanning.
- `robot/`: firmwaremodules voor de echte ESP32 en hun configuratie.
- `simulatie/`: offline simulatie en PyQt6-weergave.
- `tests/`: computerproeven en offscreen-venstertests.

Gebruik `requirements-sim.txt` (correct gespeld). De virtuele omgeving .venv
hoort niet in Git. De echte robotconfiguratie moet op de baan gevalideerd
worden; een succesvolle computerrit bewijst geen fysieke sensorherkenning.

## Testen en uitleg

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Lees `simulatie/README.md` voor de bediening en grenzen, `GEDEELD_API.md` voor
de gegevensstructuren, `data/README.md` voor de kaart en `robot/README.md` voor
de ESP32-instellingen en uploadprocedure.
