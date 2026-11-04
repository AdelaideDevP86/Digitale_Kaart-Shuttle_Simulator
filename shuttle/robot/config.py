"""Afstelling uit de eerdere robotcode. Bevestig de hardware op jullie bord."""
import time

KAARTPAD = "data/parcours.json"
HARDWARE_BEVESTIGD = False
STARTPOSITIE_BEVESTIGD = False  # Alleen True als hij werkelijk in D00 klaarstaat.
LOKALE_BESTEMMINGEN = ()       # Bijvoorbeeld ('WILDWATER', 'FREEFALL'); anders MQTT.

HARDWARE = {
    "sensor_pinnen": (2, 1, 7, 6, 5),  # Fysiek van links naar rechts.
    "zwart": 0,
    "links_richting": 12, "rechts_richting": 13,
    "links_pwm": 11, "rechts_pwm": 17,
    "links_vooruit": 1, "rechts_vooruit": 0,
    "pwm_hz": 1000,
}
RIJDEN = {
    "basis": 0.35, "draaien": 0.35, "zoeken": 0.35,
    "kp": 0.60, "ki": 0.0, "kd": 0.15,
    "max_i": 2.0, "d_venster_ms": 50, "d_metingen": 10,
    "min_motor": -0.15,
    "lijn_ms": 25, "uitlijnen_ms": 0,
    "keer_min_ms": 700, "keer_richting": "links",
    "positie_onzeker_ms": 500,
    "marker_ms": 500,
}
DETECTOR = {"breed_ms": 10, "vrij_ms": 25}
LUS_MS = 5
STATUS_INTERVAL_MS = 1000
WIFI_SSID = None
WIFI_WACHTWOORD = ""
OBJECT = {"aan": False, "stop_mm": 180, "vrij_mm": 230,
          "meet_interval_ms": 50, "max_leeftijd_ms": 200}

MQTT = {
    "broker": None,           # Zelf invullen; None houdt netwerk uit.
    "poort": 1883,
    "gebruiker": None, "wachtwoord": None,
    "robot_id": "robot01", "prefix": "school/shuttle",
    "keepalive_s": 30, "herverbinden_ms": 5000,
    "max_bericht_bytes": 2048, "inbox_max": 8, "ack_max": 16,
}


def nu_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def verschil_ms(nu, toen):
    return time.ticks_diff(nu, toen) if hasattr(time, "ticks_diff") else nu - toen


def slaap_ms(duur):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(duur)
    else:
        time.sleep(duur / 1000)
