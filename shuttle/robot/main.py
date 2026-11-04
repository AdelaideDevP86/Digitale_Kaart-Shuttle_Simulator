"""Op de ESP32: robot/, gedeeld/, data/ plus een klein root-main.py uploaden."""
from . import config, hardware
from .kruispunt_detector import KruispuntDetector
from .objectdetectie import ObjectDetectie
from .rit_besturing import RitBesturing
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


def main():
    mqtt = None
    try:
        if not config.HARDWARE_BEVESTIGD:
            raise ValueError("Controleer pinnen/polariteit en zet HARDWARE_BEVESTIGD in robot/config.py")
        kaart = ParcoursKaart.uit_bestand(config.KAARTPAD)
        # De huidige data zijn bewust logisch: eerst echte serviceplaatsen invullen.
        kaart.controleer_robotprofiel(list(kaart.attracties))
        hardware.initialiseer(config.HARDWARE)
        detector = KruispuntDetector(config.DETECTOR)
        mqtt = RobotMqtt(config.MQTT)
        besturing = RitBesturing(RoutePlanner(kaart), detector, mqtt, hardware.rijd)
        objecten = ObjectDetectie(config.OBJECT)
        if config.STARTPOSITIE_BEVESTIGD:
            besturing.bevestig_start()
        verbind_wifi()
        if config.LOKALE_BESTEMMINGEN:
            mqtt.voer_in({"command_id": "lokale-start", "command_seq": 1,
                          "robot_id": mqtt.robot_id, "sessie_id": mqtt.sessie_id,
                          "actie": "start", "mission_id": "lokale-rit", "revisie": 1,
                          "kaartversie": kaart.versie,
                          "bestemmingen": list(config.LOKALE_BESTEMMINGEN)})
        print("Robot gereed; sessie:", mqtt.sessie_id)
        while True:
            nu = config.nu_ms()
            meting = hardware.lees_meting()
            meting["obstakel"] = objecten.update(nu, meting.get("afstand_mm"))
            besturing.update(nu, meting)
            # Als er al een geldig TCP-kanaal is, pollt dit tijdens rijden mee.
            mqtt.poll(nu, mag_verbinden=besturing.motoren == (0, 0))
            opdracht = mqtt.pak_opdracht()
            if opdracht is not None:
                besturing.ontvang(opdracht)
            config.slaap_ms(config.LUS_MS)
    finally:
        try:
            hardware.stop()
        finally:
            try:
                if mqtt is not None:
                    mqtt.sluit()
            finally:
                hardware.sluit()


if __name__ == "__main__":
    main()
