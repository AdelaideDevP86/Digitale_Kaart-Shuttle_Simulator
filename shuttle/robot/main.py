"""Op de ESP32: robot/, gedeeld/, data/ plus een klein root-main.py uploaden."""
from . import config, hardware
from .kruispunt_detector import KruispuntDetector
from .objectdetectie import ObjectDetectie
from .rit_besturing import RitBesturing
from .rit_log import RitLog
from .robot_mqtt import RobotMqtt
from gedeeld import ParcoursKaart, RoutePlanner


def verbind_wifi():
    # Roep alleen bij opstarten aan, met stilstaande motoren.
    import network
    ssid = getattr(config, "WIFI_SSID", None)
    if not ssid:
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, getattr(config, "WIFI_WACHTWOORD", ""))
    start = config.nu_ms()
    while not wlan.isconnected() and config.verschil_ms(config.nu_ms(), start) < 10000:
        config.slaap_ms(50)
    return wlan


def controleer_start(kaart, bestemmingen):
    # MQTT-doelen worden pas bij ontvangst gevalideerd. De drie andere
    # attracties hoeven voor een lokale rit met twee haltes niet klaar te zijn.
    kaart.controleer_robotprofiel(list(bestemmingen))


def main():
    mqtt = None
    besturing = None
    log = RitLog(config.LOG)
    laatste_toestand = None
    log.event(config.nu_ms(), "opstart", {"kaartpad": config.KAARTPAD})
    try:
        if not config.HARDWARE_BEVESTIGD:
            raise ValueError("Controleer pinnen/polariteit en zet HARDWARE_BEVESTIGD in robot/config.py")
        kaart = ParcoursKaart.uit_bestand(config.KAARTPAD)
        controleer_start(kaart, config.LOKALE_BESTEMMINGEN)
        print("Besturing:", config.BESTURING_VERSIE)
        hardware.initialiseer(config.HARDWARE)
        detector = KruispuntDetector(config.DETECTOR)
        mqtt = RobotMqtt(config.MQTT)
        besturing = RitBesturing(RoutePlanner(kaart), detector, mqtt, hardware.rijd, log=log)
        objecten = ObjectDetectie(config.OBJECT)
        if config.STARTPOSITIE_BEVESTIGD:
            besturing.bevestig_start()
        verbind_wifi()
        if config.LOKALE_BESTEMMINGEN:
            print("Start over", config.START_WACHTTIJD_MS // 1000, "s: zet de robot neer")
            config.slaap_ms(config.START_WACHTTIJD_MS)
            mqtt.voer_in({"command_id": "lokale-start", "command_seq": 1,
                          "robot_id": mqtt.robot_id, "sessie_id": mqtt.sessie_id,
                          "actie": "start", "mission_id": "lokale-rit", "revisie": 1,
                          "kaartversie": kaart.versie,
                          "bestemmingen": list(config.LOKALE_BESTEMMINGEN)})
            opdracht = mqtt.pak_opdracht()
            resultaat = besturing.ontvang(opdracht)
            if resultaat["resultaat"] != "accepted":
                raise ValueError("Lokale rit geweigerd: " + resultaat.get("reden", "onbekend"))
            print("LOKALE ROUTE:", " -> ".join(config.LOKALE_BESTEMMINGEN), "-> DEPOT")
            print("Robot gereed; kaart:", kaart.versie, "sessie:", mqtt.sessie_id)
        while True:
            nu = config.nu_ms()
            meting = hardware.lees_meting()
            meting["obstakel"] = objecten.update(nu, meting.get("afstand_mm"))
            besturing.update(nu, meting)
            if (besturing.toestand not in ("GEREED", "GESTOPT", "KLAAR")
                    or besturing.toestand != laatste_toestand):
                log.meet(nu, meting, besturing)
            if besturing.toestand != laatste_toestand:
                print(nu, besturing.toestand, "stap", besturing.stapindex,
                      "naar", besturing._verwacht, besturing.reden)
                if besturing.toestand in ("GESTOPT", "KLAAR"):
                    try:
                        log.schrijf(besturing)
                        print("Log opgeslagen:", config.LOG["pad"])
                    except OSError as fout:
                        print("Log schrijven mislukt:", fout)
                laatste_toestand = besturing.toestand
            # Als er al een geldig TCP-kanaal is, pollt dit tijdens rijden mee.
            mqtt.poll(nu, mag_verbinden=besturing.motoren == (0, 0))
            opdracht = mqtt.pak_opdracht()
            if opdracht is not None:
                print("OPDRACHT:", besturing.ontvang(opdracht))
            config.slaap_ms(config.LUS_MS)
    except Exception as fout:
        log.event(config.nu_ms(), "exception", {"reden": str(fout)})
        raise
    finally:
        try:
            hardware.stop()
        finally:
            try:
                # Bij een exception kunnen de bewaarde motorwaarden achterlopen;
                # hardware.stop() is hierboven eerst uitgevoerd.
                try:
                    log.schrijf()
                except OSError as fout:
                    print("Log schrijven mislukt:", fout)
                if mqtt is not None:
                    mqtt.sluit()
            finally:
                hardware.sluit()


if __name__ == "__main__":
    main()
