import unittest
import sayo
import device
from sayo_config import App


class FakeHID:
    def __init__(self):
        self.keys = {}
        for n in range(device.NUM_KEYS):
            rec = bytearray(46)
            rec[0] = 0
            rec[1] = n
            rec[2] = 1
            rec[device.V1] = sayo.KEYS["1"]
            self.keys[n] = rec
        self.saved = False
        self._reply = None

    def write(self, frame):
        cmd, n = frame[1], frame[2]
        payload = frame[3:3 + n]
        if cmd == device.CMD_IDENTIFY:
            self._reply = self._frame(b"\x08\x9a\x00\x05")
        elif cmd == device.CMD_SAVE:
            self.saved = True
            self._reply = self._frame(b"")
        elif cmd == device.CMD_KEY:
            kn = payload[1]
            if payload[0] == 1:
                self.keys[kn] = bytearray(payload)
            self._reply = self._frame(bytes(self.keys[kn]))

    def read(self, size, timeout=1000):
        return list(self._reply)

    @staticmethod
    def _frame(payload):
        body = bytes([0x02, 0x00, len(payload)]) + payload
        body += bytes([sum(body) & 0xFF])
        return body + bytes(64 - len(body))


class FakeV2HID:
    def __init__(self):
        self.records = {}
        for n in range(device.NUM_KEYS):
            record = bytearray(64)
            record[0:8] = bytes([device.V2_REPORT_ID, device.V2_COMMAND, 0, 0,
                                 0x3C, 0, device.V2_LIGHT, n])
            record[28:31] = bytes([255, 255, 255])
            self.records[n] = record
        self._reply = None

    def write(self, packet):
        packet = bytearray(packet)
        n = packet[7]
        if packet[4] == 0x3C:  # write
            self.records[n] = packet
        self._reply = self.records[n]
        return len(packet)

    def read(self, size, timeout=1000):
        return list(self._reply)


class LedTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHID()
        self.dev = device.Device(self.fake)
        self.led = FakeV2HID()
        self.dev.led_h = self.led

    def _make_app(self):
        app = App.__new__(App)
        app.device = self.dev
        app.device_module = device
        app.bindings = {n + 1: "1" for n in range(12)}
        app.colors = {n + 1: "#FFFFFF" for n in range(12)}
        app.press_lighting = {n + 1: False for n in range(12)}
        app.saved_records = {n: bytes(self.dev.read_key(n)) for n in range(12)}
        app.markers_installed = True
        app.warning = None
        app.active = None
        app.pending = None
        app.pending_color = None
        app.pending_press_lighting = None
        app.ready = True
        app.error = None
        app.message = ""
        return app

    def test_write_and_read_led(self):
        self.dev.write_led(0, 255, 0, 128)
        self.assertEqual(tuple(self.led.records[0][28:31]), (255, 0, 128))
        color = self.dev.read_led(0)
        self.assertEqual(color, (255, 0, 128))

    def test_press_only_lighting_sets_the_firmware_event(self):
        app = self._make_app()
        app.select(1)
        app.set_press_lighting(1, True)
        app.select(1)

        self.assertTrue(self.fake.saved)
        self.assertTrue(app.press_lighting[1])
        self.assertEqual(self.led.records[0][25], device.LED_EVENT_PRESS_ON_RELEASE_OFF)

    def test_set_color_and_save_on_key_toggle(self):
        app = self._make_app()
        # Select key 2
        app.select(2)
        self.assertEqual(app.active, 2)

        # Set color to Cyan (#00FFFF)
        app.set_color(2, "#00FFFF")
        self.assertEqual(app.pending_color, "#00FFFF")

        # Click key 2 again to save
        self.fake.saved = False
        app.select(2)

        self.assertTrue(self.fake.saved)
        self.assertEqual(tuple(self.led.records[1][28:31]), (0, 255, 255))
        self.assertEqual(app.colors[2], "#00FFFF")
        self.assertIsNone(app.active)
        self.assertIsNone(app.pending_color)

    def test_save_both_binding_and_color(self):
        app = self._make_app()
        app.select(3)
        app.pending = "cmd+c"
        app.set_color(3, "#FF0000")

        self.fake.saved = False
        app.select(3)

        self.assertTrue(self.fake.saved)
        self.assertEqual(tuple(self.led.records[2][28:31]), (255, 0, 0))
        self.assertEqual(app.colors[3], "#FF0000")
        self.assertEqual(app.bindings[3], "cmd+c")

    def test_switching_key_discards_unsaved_color(self):
        app = self._make_app()
        app.select(1)
        app.set_color(1, "#00FF00")
        self.assertEqual(app.pending_color, "#00FF00")

        # Switch to key 2 instead of saving key 1
        app.select(2)
        self.assertEqual(app.active, 2)
        self.assertIsNone(app.pending_color)
        self.assertEqual(app.colors[1], "#FFFFFF")


if __name__ == "__main__":
    unittest.main()
