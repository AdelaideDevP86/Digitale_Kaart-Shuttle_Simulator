import json
import unittest
from robot import config
from robot.robot_mqtt import RobotMqtt, _pakket, _tekstveld
from tests.test_besturing_detector import Proef


class MqttTests(unittest.TestCase):
    def test_dubbele_opdracht_geen_tweede_rit(self):
        p = Proef(); p.stuur()
        oud = dict(p.b.opdracht)
        for _ in range(3):
            p.mqtt.voer_in(oud)
            self.assertIsNone(p.mqtt.pak_opdracht())
        p.ronde()
        p.mqtt.voer_in(oud)
        self.assertIsNone(p.mqtt.pak_opdracht())
        self.assertEqual(p.b.toestand, 'KLAAR')
        self.assertEqual(p.mqtt.uitgaande[-1]['resultaat'], 'duplicate')

    def test_cache_ouder_dan_32_blijft_oud(self):
        p = Proef()
        for _ in range(35):
            p.stuur('stop')
        oud = dict(command_id='cmd-1', command_seq=1, robot_id=p.mqtt.robot_id,
                   sessie_id=p.mqtt.sessie_id, actie='stop')
        p.mqtt.voer_in(oud)
        self.assertIsNone(p.mqtt.pak_opdracht())
        self.assertEqual(p.mqtt.uitgaande[-1]['reden'], 'Verouderd command_seq')
        self.assertEqual(len(p.mqtt.recente_opdrachten), 32)

    def test_verkeerde_sessie_retained_kapotte_json(self):
        p = Proef()
        for bericht, retain in [(b'{', False), (b'[]',False), (b'{}',True)]:
            p.mqtt.voer_in(bericht, retained=retain)
            self.assertIsNone(p.mqtt.pak_opdracht())
        self.assertEqual(p.stuur(sessie_id='oude-boot')['resultaat'], 'gefilterd')
        self.assertEqual(p.mqtt.hoogste_command_seq, 0)

    def test_semantisch_fout_wist_rit_niet(self):
        p = Proef(); p.stuur()
        plan = p.b.plan
        self.assertEqual(p.stuur('vervang', ['FOUT'], 2)['resultaat'], 'rejected')
        self.assertIs(p.b.plan, plan)
        self.assertIsNone(p.b.wachtend)

    def test_oude_sessie_na_reset(self):
        p = Proef(); p.stuur()
        nieuw = RobotMqtt(config.MQTT, 'nieuwe-boot', 'simulatie')
        nieuw.voer_in(p.b.opdracht)
        self.assertIsNone(nieuw.pak_opdracht())

    def test_stop_voorrang_op_inbox(self):
        p = Proef()
        base = dict(command_id='a', command_seq=1, robot_id=p.mqtt.robot_id,
                    sessie_id=p.mqtt.sessie_id, actie='start')
        p.mqtt.voer_in(base)
        p.mqtt.voer_in(dict(base, command_id='b',command_seq=2,actie='stop'))
        self.assertEqual(p.mqtt.pak_opdracht()['actie'], 'stop')
        self.assertIsNone(p.mqtt.pak_opdracht())

    def test_inbox_en_ack_begrensd(self):
        p = Proef()
        for i in range(100):
            p.mqtt.voer_in(dict(command_id=str(i), command_seq=i+1, robot_id=p.mqtt.robot_id,
                               sessie_id=p.mqtt.sessie_id, actie='start'))
        self.assertLessEqual(len(p.mqtt.inbox), 8)
        self.assertLessEqual(len(p.mqtt.uitgaande),16)
        self.assertLessEqual(len(p.mqtt._afgeleverd),9)

    def test_gefragmenteerde_mqtt_handshake_en_publish(self):
        p = Proef()
        m = p.mqtt
        m._fase = 'CONNACK'
        m._rx.extend(b'\x20\x02\x00')
        m._verwerk_buffer(0)
        self.assertFalse(m.verbonden)
        m._rx.extend(b'\x00')
        m._verwerk_buffer(5)
        self.assertEqual(m._fase, 'SUBACK')
        m._rx.extend(b'\x90\x03\x00\x01\x00')
        m._verwerk_buffer(10)
        self.assertTrue(m.verbonden)
        cmd = dict(command_id='x',command_seq=1,robot_id=m.robot_id,sessie_id=m.sessie_id,actie='stop')
        wire = _pakket(0x30, _tekstveld(m.topic+'/command')+json.dumps(cmd).encode())
        for i in range(0,len(wire),3):
            m._rx.extend(wire[i:i+3]); m._verwerk_buffer(20)
        self.assertEqual(m.pak_opdracht()['command_id'], 'x')
        # Retained replay op de wire wordt evenmin als rit behandeld.
        m._rx.extend(_pakket(0x31,_tekstveld(m.topic+'/command')+json.dumps(cmd).encode()))
        m._verwerk_buffer(25)
        self.assertIsNone(m.pak_opdracht())

    def test_netwerkfout_bewaart_missie_en_status(self):
        class Stuk:
            def send(self, data): raise OSError(104)
            def close(self): pass
        p = Proef(); p.stuur(); p.tik()
        p.mqtt._sock, p.mqtt.verbonden = Stuk(), True
        p.mqtt._tx.extend(b'abc')
        p.mqtt.poll(100)
        self.assertFalse(p.mqtt.verbonden)
        self.assertIsNotNone(p.mqtt.status_wachtend)
        self.assertEqual(p.b.opdracht['mission_id'], 'rit-1')

    def test_gedeeltelijk_schrijven_wacht_niet_op_netwerk(self):
        class Langzaam:
            def send(self, data): return min(3,len(data))
            def recv(self, n): raise OSError(11)
            def close(self): pass
        p = Proef()
        p.mqtt._sock, p.mqtt.verbonden = Langzaam(), True
        p.mqtt._tx.extend(b'abcdefghi')
        p.mqtt.poll(0)
        self.assertEqual(bytes(p.mqtt._tx), b'defghi')
        p.mqtt.poll(5)
        self.assertEqual(bytes(p.mqtt._tx), b'ghi')
        p.mqtt.poll(10)
        self.assertEqual(bytes(p.mqtt._tx), b'')


if __name__ == '__main__':
    unittest.main()
