# Arcade-terugweg: J12-passage

Versie: `KRUISPUNT_TERUGWEG_20261105_2`.

De laatste rit in de aangeleverde log stopt op stap 6 om 19508 ms met
`Kruispunt blijft afwijken van geplande uitgang`, terwijl J12 verwacht wordt.
Dat is het Arcade-kruispunt op de terugweg, geen bevestigde depotaankomst.

De kaart blijft ongewijzigd. Bij aankomst uit S02 over E32 heeft J12 links
de verbinding E30 en rechtdoor E31 naar J11. De route vraagt rechtdoor.
De sensoren melden eerst `00111` (rechts) en daarna `11111` (beide zijden).
De oude controle onthoudt de rechterzijde en blijft die als onmogelijke poort
afwijzen, ook als de verwachte linkerzijde later correct bevestigd is.

De nieuwe controle vereist positief bewijs voor de gewenste uitgang:

- Links/rechts afslaan vereist nog steeds bevestiging van die gevraagde kant.
  De al bestaande uitzondering voor de laatste T vanaf J01 naar D00 blijft:
  daar bevestigt de andere arm van de T de passage ook.
- Rechtdoor vereist dat dit volgens de kaart mogelijk is en dat een verwachte
  zijtak bevestigd is. Bij J12 op deze terugweg is dat links.
- Een extra gemeten zijde maakt die bevestiging niet meer ongeldig.
- Alleen rechts zien terwijl J12 links verwacht blijft onvoldoende bewijs.
- Een gewone uitgaande lijn blijft nodig voordat de rijstap wordt afgerond.
  Helemaal wit na het brede stuk is dus geen geslaagde passage: dan blijft
  kort lijnherstel nodig. Extra zijden negeren herstelt geen fysieke lijn.

In `punt_bevestigd` en het nieuwe `punt_afwijking` staan nu ook de geplande
actie en de mogelijke kaartuitgangen. Dat maakt een volgende log gerichter.
De huidige Arcade-route, snelheden, PID, timers en depotherkenning blijven
gelijk. Deze wijziging corrigeert de zijdencontrole, geen fysieke afstelling.

Upload de twee gewijzigde robotbestanden vanuit de map shuttle:

```text
cp robot/config.py :robot/config.py
cp robot/rit_besturing.py :robot/rit_besturing.py
```

Start opnieuw vanuit D00 met de console zichtbaar. Controleer op
`Besturing: KRUISPUNT_TERUGWEG_20261105_2`.

De zes nieuwe tests spelen de volgorde rechts -> beide -> gewone lijn na,
controleren de volledige terugweg en blijven een afwezige gevraagde richting
en ontbrekende uitgaande lijn afwijzen. Dit zijn proeven met synthetische
sensorreeksen; de robotrit moet op de baan worden gecontroleerd.
