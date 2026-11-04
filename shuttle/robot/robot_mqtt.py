"""MQTT 3.1.1 over TCP met incrementeel lezen/schrijven en applicatie-ACK.

Geen extra MQTT-pakket nodig. Alleen DNS/TCP verbinden kan blokkeren; main
staat dat uitsluitend toe met stilstaande motoren. De bestaande verbinding
wordt tijdens rijden niet-blokkerend onderhouden. TLS is hier niet ingebouwd.
"""
import json
from .config import nu_ms, verschil_ms


def _tekstveld(tekst):
    data = tekst.encode() if isinstance(tekst, str) else tekst
    if len(data) > 65535:
        raise ValueError("MQTT-tekstveld is te lang")
    return bytes((len(data) >> 8, len(data) & 255)) + data


def _pakket(header, inhoud=b""):
    lengte, gecodeerd = len(inhoud), bytearray()
    while True:
        cijfer = lengte % 128
        lengte //= 128
        gecodeerd.append(cijfer | (128 if lengte else 0))
        if not lengte:
            break
    return bytes((header,)) + bytes(gecodeerd) + inhoud


class RobotMqtt:
    def __init__(self, instellingen, sessie_id=None, bron="robot"):
        if bron not in ("robot", "simulatie"):
            raise ValueError("Onbekende berichtbron")
        self.instellingen = dict(instellingen)
        self.bron = bron
        self.robot_id = instellingen["robot_id"] if bron == "robot" else "sim-" + instellingen["robot_id"]
        if sessie_id is None:
            import os
            from binascii import hexlify
            sessie_id = hexlify(os.urandom(12)).decode()
        self.sessie_id = sessie_id
        prefix = instellingen["prefix"].rstrip("/")
        if bron == "simulatie":
            prefix += "/simulatie"
        self.topic = prefix + "/" + self.robot_id
        self.inbox, self.uitgaande = [], []
        self.recente_opdrachten, self._volgorde = {}, []
        self.hoogste_command_seq = 0
        self._afgeleverd = {}
        self.status_wachtend = None
        self.verbonden = False
        self.fout = None
        self._sock = None
        self._fase = None
        self._rx, self._tx = bytearray(), bytearray()
        self._poging_ms = None
        self._verkeer_ms = self._verbinden_ms = 0
        self._ping_ms = None

    def _ack(self, command_id, resultaat, reden="", oorspronkelijk=None):
        bericht = {"robot_id": self.robot_id, "sessie_id": self.sessie_id,
                   "command_id": command_id, "resultaat": resultaat, "reden": reden}
        if oorspronkelijk is not None:
            bericht["oorspronkelijk"] = oorspronkelijk
        if len(self.uitgaande) >= self.instellingen.get("ack_max", 16):
            self.uitgaande.pop(0)  # De afzender kan dezelfde ID opnieuw proberen.
        self.uitgaande.append(bericht)

    def controleer_opdracht(self, opdracht):
        if not isinstance(opdracht, dict):
            self._ack(None, "rejected", "Opdracht moet een object zijn")
            return False
        cid = opdracht.get("command_id")
        reden = None
        if not isinstance(cid, str) or not cid.strip() or len(cid) > 80:
            reden = "Ongeldig command_id"
        elif opdracht.get("robot_id") != self.robot_id or opdracht.get("sessie_id") != self.sessie_id:
            reden = "Verkeerde robot of sessie"
        elif opdracht.get("actie") not in ("start", "vervang", "stop"):
            reden = "Onbekende actie"
        elif type(opdracht.get("command_seq")) is not int or opdracht["command_seq"] <= 0:
            reden = "Ongeldig command_seq"
        elif cid in self.recente_opdrachten:
            oud, resultaat, oud_reden = self.recente_opdrachten[cid]
            if oud != opdracht:
                self._ack(cid, "rejected", "Bestaande ID met gewijzigde inhoud")
            else:
                self._ack(cid, "duplicate", oud_reden, resultaat)
            return False
        elif opdracht["command_seq"] <= self.hoogste_command_seq:
            reden = "Verouderd command_seq"
        if reden:
            self._ack(cid if isinstance(cid, str) else None, "rejected", reden)
            return False
        # Snapshot voor de latere semantische bevestiging door RitBesturing.
        self._afgeleverd[cid] = json.loads(json.dumps(opdracht))
        # Alleen binnen inbox/hoofdloop nodig; voorkom groei bij afgewezen berichten.
        while len(self._afgeleverd) > self.instellingen.get("inbox_max", 8) + 1:
            self._afgeleverd.pop(next(iter(self._afgeleverd)))
        return True

    def voer_in(self, data, retained=False):
        if retained:
            self._ack(None, "rejected", "Retained opdrachten worden geweigerd")
            return
        try:
            if isinstance(data, dict):
                data = json.dumps(data).encode()
            elif isinstance(data, str):
                data = data.encode()
            if not isinstance(data, bytes) or len(data) > self.instellingen.get("max_bericht_bytes", 2048):
                raise ValueError("Bericht te groot of geen tekst")
            opdracht = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError, TypeError):
            self._ack(None, "rejected", "Ongeldige JSON of berichtlengte")
            return
        if not self.controleer_opdracht(opdracht):
            return
        if opdracht["actie"] == "stop":
            self.inbox[:] = [opdracht]  # STOP heeft voorrang op nog ongelezen opdrachten.
        elif len(self.inbox) >= self.instellingen.get("inbox_max", 8):
            self._ack(opdracht["command_id"], "rejected", "Inbox vol; probeer opnieuw")
        else:
            self.inbox.append(opdracht)

    def pak_opdracht(self):
        while self.inbox:
            opdracht = self.inbox.pop(0)
            if self.controleer_opdracht(opdracht):
                return opdracht
        return None

    def bevestig(self, command_id, resultaat, reden=""):
        if command_id in self.recente_opdrachten:
            oud, _, _ = self.recente_opdrachten[command_id]
            self.recente_opdrachten[command_id] = (oud, resultaat, reden)
        elif resultaat in ("accepted", "pending", "applied") and command_id in self._afgeleverd:
            opdracht = self._afgeleverd[command_id]
            self.hoogste_command_seq = max(self.hoogste_command_seq, opdracht["command_seq"])
            self.recente_opdrachten[command_id] = (opdracht, resultaat, reden)
            self._volgorde.append(command_id)
            if len(self._volgorde) > 32:
                self.recente_opdrachten.pop(self._volgorde.pop(0))
        self._afgeleverd.pop(command_id, None)
        self._ack(command_id, resultaat, reden)

    def publiceer_status(self, status):
        bericht = dict(status)
        bericht.update(robot_id=self.robot_id, sessie_id=self.sessie_id, bron=self.bron)
        self.status_wachtend = bericht
        self._laatste_status = bericht

    def sluit(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock, self._fase = None, None
        self.verbonden = False
        self._rx, self._tx = bytearray(), bytearray()
        self._ping_ms = None
        if hasattr(self, "_laatste_status"):
            self.status_wachtend = self._laatste_status

    def _verbind(self, nu):
        import socket
        c = self.instellingen
        host = c.get("broker")
        if not isinstance(host, str) or not host.strip():
            return
        gebruiker, wachtwoord = c.get("gebruiker"), c.get("wachtwoord")
        if wachtwoord and not gebruiker:
            raise ValueError("MQTT-wachtwoord vereist een gebruiker")
        sock = socket.socket()
        self._sock = sock
        sock.settimeout(1)
        adres = socket.getaddrinfo(host, c["poort"], 0, socket.SOCK_STREAM)[0][-1]
        sock.connect(adres)
        sock.setblocking(False)
        vlaggen = 2 | (128 if gebruiker else 0) | (64 if gebruiker and wachtwoord is not None else 0)
        keepalive = c.get("keepalive_s", 30)
        inhoud = _tekstveld("MQTT") + bytes((4, vlaggen, keepalive >> 8, keepalive & 255))
        inhoud += _tekstveld(self.robot_id + "-" + self.sessie_id)
        if gebruiker:
            inhoud += _tekstveld(gebruiker)
            if wachtwoord is not None:
                inhoud += _tekstveld(wachtwoord)
        self._tx.extend(_pakket(0x10, inhoud))
        self._fase = "CONNACK"
        self._verbinden_ms = self._verkeer_ms = nu

    @staticmethod
    def _zou_blokkeren(fout):
        return bool(fout.args) and fout.args[0] in (11, 35, 10035, 115)

    def _ontleed(self, header, inhoud, nu):
        soort = header >> 4
        if soort == 2:
            if self._fase != "CONNACK" or len(inhoud) != 2 or inhoud[1] != 0:
                raise ValueError("Broker weigert CONNECT of CONNACK is ongeldig")
            self._tx.extend(_pakket(0x82, b"\x00\x01" + _tekstveld(self.topic + "/command") + b"\x00"))
            self._fase = "SUBACK"
        elif soort == 9:
            if self._fase != "SUBACK" or inhoud != b"\x00\x01\x00":
                raise ValueError("Broker weigert de QoS0-subscription")
            self._fase, self.verbonden = "KLAAR", True
        elif soort == 3:
            if not self.verbonden or len(inhoud) < 2:
                raise ValueError("Onverwacht of kort PUBLISH-pakket")
            lengte = inhoud[0] * 256 + inhoud[1]
            einde = 2 + lengte
            if einde > len(inhoud):
                raise ValueError("Onvolledig topic")
            topic = inhoud[2:einde].decode()
            qos = (header >> 1) & 3
            if qos == 1:
                if einde + 2 > len(inhoud):
                    raise ValueError("Packet-ID ontbreekt")
                self._tx.extend(_pakket(0x40, inhoud[einde:einde + 2]))
                einde += 2
            elif qos != 0:
                raise ValueError("Niet ondersteunde inkomende QoS")
            if topic == self.topic + "/command":
                self.voer_in(inhoud[einde:], retained=bool(header & 1))
        elif soort == 13:
            if inhoud:
                raise ValueError("Ongeldige PINGRESP")
            self._ping_ms = None
        else:
            raise ValueError("Onverwacht MQTT-pakket: " + str(soort))
        self._verkeer_ms = nu

    def _verwerk_buffer(self, nu):
        for _ in range(4):  # Begrens werk per besturingscyclus.
            if len(self._rx) < 2:
                return
            lengte, factor, i = 0, 1, 1
            while True:
                if i >= len(self._rx):
                    return
                cijfer = self._rx[i]
                lengte += (cijfer & 127) * factor
                i += 1
                if lengte > self.instellingen.get("max_bericht_bytes", 2048) + 256:
                    raise ValueError("MQTT-frame te groot")
                if not cijfer & 128:
                    break
                if i >= 5:
                    raise ValueError("Ongeldige MQTT-lengte")
                factor *= 128
            if len(self._rx) < i + lengte:
                return
            header, inhoud = self._rx[0], bytes(self._rx[i:i + lengte])
            del self._rx[:i + lengte]
            self._ontleed(header, inhoud, nu)

    def poll(self, nu=None, mag_verbinden=False):
        nu = nu_ms() if nu is None else nu
        try:
            if self._sock is None:
                if (mag_verbinden and self.instellingen.get("broker") and
                        (self._poging_ms is None or verschil_ms(nu, self._poging_ms) >= self.instellingen.get("herverbinden_ms", 5000))):
                    self._poging_ms = nu
                    self._verbind(nu)
                return
            if not self.verbonden and verschil_ms(nu, self._verbinden_ms) > 5000:
                raise OSError("MQTT-handshake timeout")
            if self._ping_ms is not None and verschil_ms(nu, self._ping_ms) > 10000:
                raise OSError("MQTT-ping timeout")
            if self.verbonden and not self._tx:
                if self.uitgaande:
                    bericht = self.uitgaande.pop(0)
                    self._tx.extend(_pakket(0x30, _tekstveld(self.topic + "/ack") + json.dumps(bericht).encode()))
                elif self.status_wachtend is not None:
                    self._tx.extend(_pakket(0x31, _tekstveld(self.topic + "/status") + json.dumps(self.status_wachtend).encode()))
                    self.status_wachtend = None
                elif self._ping_ms is None and verschil_ms(nu, self._verkeer_ms) >= self.instellingen.get("keepalive_s", 30) * 500:
                    self._tx.extend(_pakket(0xC0))
                    self._ping_ms = nu
            if self._tx:
                try:
                    aantal = self._sock.send(bytes(self._tx[:512]))
                    if aantal:
                        del self._tx[:aantal]
                        self._verkeer_ms = nu
                except OSError as fout:
                    if not self._zou_blokkeren(fout):
                        raise
            try:
                ontvangen = self._sock.recv(1024)
                if ontvangen == b"":
                    raise OSError("Broker heeft verbinding gesloten")
                self._rx.extend(ontvangen)
            except OSError as fout:
                if not self._zou_blokkeren(fout):
                    raise
            if len(self._rx) > 8192:
                raise ValueError("MQTT-ontvangbuffer te groot")
            self._verwerk_buffer(nu)
        except (OSError, ValueError, UnicodeError) as fout:
            self.fout = str(fout)
            self.sluit()
