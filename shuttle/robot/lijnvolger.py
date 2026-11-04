"""PID, zoeken en draaien als korte rekenfuncties, zonder wachtlussen."""


def geldig(patroon):
    return isinstance(patroon, str) and len(patroon) == 5 and all(c in "01" for c in patroon)


def gewone_lijn(p):
    return geldig(p) and p[0] == p[4] == "0" and "1" in p[1:4]


def startlijn(p):
    return (geldig(p) and p[2] == "1" and 1 <= p.count("1") <= 3
            and "0" not in p.strip("0"))


def nieuwe_pid():
    return {"historie": [], "integraal": 0.0, "vorige_ms": None, "richting": "links"}


def reset_pid(toestand):
    richting = toestand.get("richting", "links")
    toestand.clear()
    toestand.update(nieuwe_pid())
    toestand["richting"] = richting


def draaicommando(richting, snelheid):
    if richting not in ("links", "rechts"):
        raise ValueError("Draairichting moet links of rechts zijn")
    return (-snelheid, snelheid) if richting == "links" else (snelheid, -snelheid)


def volg_lijn(patroon, nu, toestand, instellingen):
    """nu is een oplopende actieve tijd in ms; D behoudt het oude 50ms-venster."""
    if not geldig(patroon) or "1" not in patroon:
        raise ValueError("Geen geldige lijnmeting voor PID")
    zwart = [i * 100 for i, bit in enumerate(patroon) if bit == "1"]
    fout = (200 - sum(zwart) / len(zwart)) / 200
    vorige = toestand["vorige_ms"]
    dt = max(0, nu - vorige) / 1000 if vorige is not None else 0
    toestand["vorige_ms"] = nu
    limiet = instellingen["max_i"]
    toestand["integraal"] = max(-limiet, min(limiet, toestand["integraal"] + fout * dt))
    historie = toestand["historie"]
    d = 0
    if historie and nu > historie[0][0]:
        d = (fout - historie[0][1]) * instellingen["d_venster_ms"] / (nu - historie[0][0])
    historie.append((nu, fout))
    while len(historie) > instellingen["d_metingen"]:
        historie.pop(0)
    correctie = (instellingen["kp"] * fout + instellingen["ki"] * toestand["integraal"]
                 + instellingen["kd"] * d)
    if fout:
        toestand["richting"] = "links" if fout > 0 else "rechts"
    basis = instellingen["basis"]
    begrens = lambda waarde: max(instellingen["min_motor"], min(basis, waarde))
    return begrens(basis - correctie), begrens(basis + correctie)
