"""Afstelling uit de eerdere robotcode. Bevestig de hardware op jullie bord."""
import time

BESTURING_VERSIE = "KRUISPUNT_TERUGWEG_20261105_2"
KAARTPAD = "data/parcours_robot.json"
HARDWARE_BEVESTIGD = True  # Bestaande pinnen/polariteit uit jullie rijdende robot.
STARTPOSITIE_BEVESTIGD = True  # Iedere herstart: fysiek in D00, richting J01 zetten.
LOKALE_BESTEMMINGEN = ("ARCADE",)

HARDWARE = {
    "sensor_pinnen": (2, 1, 7, 6, 5),  # Fysiek van links naar rechts.
    "zwart": 0,
    "links_richting": 12, "rechts_richting": 13,
    "links_pwm": 11, "rechts_pwm": 17,
    "links_vooruit": 1, "rechts_vooruit": 0,
    "pwm_hz": 1000,
}
RIJDEN = {
    "basis": 0.35, "draaien": 0.30, "zoeken": 0.35,
    "kp": 0.75 ,"ki": 0.0, "kd": 0.15,
    "max_i": 2.0, "d_venster_ms": 50, "d_metingen": 10,
    "min_motor": -0.15,
    "lijn_ms": 25, "uitlijnen_ms": 120,
    "keer_min_ms": 700, "terug_max_ms": 800, "terug_snelheid": 0.35, "keer_richting": "links",
    "positie_onzeker_ms": 1800, "zoek_timeout_ms": 8000,
    "beweging_timeout_ms": 6000,
    "zijden_ms": 10, "kruispunt_timeout_ms": 250,
    "lijneinde_ms": 100, "halte_basis":0.25,
    "marker_ms": 500, "marker_timeout_ms": 1500,
}
DETECTOR = {"breed_ms": 10, "vrij_ms": 25, "zijden_ms": 10}
LUS_MS = 5
START_WACHTTIJD_MS = 7000
STATUS_INTERVAL_MS = 1000
LOG = {"pad": "ritlog.jsonl", "events_max": 128, "metingen_max": 160,
       "meet_interval_ms": 100}
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
