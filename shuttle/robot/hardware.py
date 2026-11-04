"""Alleen hier worden echte GPIO/PWM-objecten aangemaakt, niet bij import."""
_pwm = []
_richting = []
_sensoren = []
_instellingen = None


def initialiseer(instellingen, machine_module=None):
    global _instellingen
    sluit()
    if machine_module is None:
        import machine as machine_module
    pinnen = list(instellingen["sensor_pinnen"]) + [instellingen[k] for k in
             ("links_richting", "rechts_richting", "links_pwm", "rechts_pwm")]
    if len(instellingen["sensor_pinnen"]) != 5 or len(set(pinnen)) != len(pinnen):
        raise ValueError("Verwacht vijf sensoren en unieke GPIO-pinnen")
    if instellingen["zwart"] not in (0, 1):
        raise ValueError("Ongeldige sensorpolariteit")
    _instellingen = dict(instellingen)
    Pin, PWM = machine_module.Pin, machine_module.PWM
    try:
        for kant in ("links", "rechts"):
            _richting.append(Pin(instellingen[kant + "_richting"], Pin.OUT))
            _pwm.append(PWM(Pin(instellingen[kant + "_pwm"]),
                            freq=instellingen["pwm_hz"], duty_u16=0))
        _sensoren.extend(Pin(n, Pin.IN) for n in instellingen["sensor_pinnen"])
        stop()
    except Exception:
        sluit()
        raise


def rijd(links, rechts):
    if len(_pwm) != 2:
        raise RuntimeError("Hardware is niet geinitialiseerd")
    for index, waarde in enumerate((links, rechts)):
        if not isinstance(waarde, (int, float)) or not -1 <= waarde <= 1:
            stop()
            raise ValueError("Motorwaarde moet tussen -1 en 1 liggen")
        vooruit = _instellingen[("links", "rechts")[index] + "_vooruit"]
        _richting[index].value(vooruit if waarde >= 0 else 1 - vooruit)
        _pwm[index].duty_u16(int(abs(waarde) * 65535))


def stop():
    fout = None
    for pwm in _pwm:
        try:
            pwm.duty_u16(0)
        except Exception as exc:
            fout = exc
    if fout is not None:
        raise fout


def lees_meting():
    if len(_sensoren) != 5:
        raise RuntimeError("Hardware is niet geinitialiseerd")
    patroon = "".join("1" if s.value() == _instellingen["zwart"] else "0" for s in _sensoren)
    return {"patroon": patroon}


def sluit():
    global _instellingen
    for pwm in _pwm:
        try:
            pwm.duty_u16(0)
        except Exception:
            pass
        try:
            pwm.deinit()
        except Exception:
            pass
    _pwm[:] = []
    _richting[:] = []
    _sensoren[:] = []
    _instellingen = None
