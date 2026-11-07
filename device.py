"""Talk to the SayoDevice 2x6V over its legacy USB HID configuration channel."""
import ctypes
import ctypes.util
import datetime
import sys
import time

try:
    import hid
except ImportError:
    hid = None

import sayo
from sayo import Combo

VID = 0x8089
PID = 0x000B                 # SayoDevice 2x6V RGB
NUM_KEYS = 12                 # protocol key numbers 0..11
V0 = 4                        # legacy record: modifier bits
V1 = 5                        # legacy record: first HID keycode

CMD_IDENTIFY = 0x00
CMD_SAVE = 0x04
CMD_KEY = 0x06               # 2x6V key map (Fn0, legacy protocol)
KEY_RECORD_SIZE = 8          # pattern, number, type, retain, four key bytes
V2_REPORT_ID = 0x21
V2_COMMAND = 0x12
V2_LIGHT = 0x11
LED_STATIC = 0
LED_EVENT_NONE = 0
LED_EVENT_PRESS_ON_RELEASE_OFF = 1


def _setup_darwin():
    """Disable exclusive HID access on macOS so the config interface can be opened."""
    if sys.platform != "darwin" or hid is None:
        return
    candidates = [
        getattr(hid, "__file__", None),
        ctypes.util.find_library("hidapi"),
        "/opt/homebrew/lib/libhidapi.dylib",
        "/usr/local/lib/libhidapi.dylib",
    ]
    for target in candidates:
        if not target:
            continue
        try:
            lib = ctypes.CDLL(target)
            if hasattr(lib, "hid_darwin_set_open_exclusive"):
                lib.hid_darwin_set_open_exclusive(0)
                return
        except Exception:
            pass


_setup_darwin()


class DeviceError(RuntimeError):
    pass


class Device:
    def __init__(self, dev=None):
        self.h = dev           # inject a fake in tests; real hid.device() otherwise
        self.led_h = None
        self._led_dirty = False

    def open(self):
        if hid is None:
            raise DeviceError("hidapi is not installed. Please run: pip install -r requirements.txt")
        _setup_darwin()
        cfg = [d for d in hid.enumerate(VID, PID)
               if d.get("interface_number") == 1
               and d.get("usage_page") == 0xFF00
               and d.get("usage") == 1]
        if not cfg:
            raise DeviceError("No SayoDevice config channel found — is it plugged in?")
        self.h = hid.device()
        try:
            self.h.open_path(cfg[0]["path"])
        except OSError as exc:
            if "open failed" in str(exc).lower() and sys.platform == "darwin":
                raise DeviceError(
                    "macOS blocked opening the keypad (open failed). "
                    "Terminal needs 'Input Monitoring' permission: go to System Settings → Privacy & Security → "
                    "Input Monitoring, ensure Terminal (or your terminal app) is enabled, then quit Terminal completely and restart it."
                ) from exc
            raise DeviceError(f"Could not open keypad: {exc}") from exc
        # This model exposes its newer RGB API as a second HID usage page. Key
        # binding writes stay on the legacy interface above; RGB uses FF11.
        led_cfg = [d for d in hid.enumerate(VID, PID)
                   if d.get("interface_number") == 1
                   and d.get("usage_page") == 0xFF11
                   and d.get("usage") == 2]
        if led_cfg:
            self.led_h = hid.device()
            try:
                self.led_h.open_path(led_cfg[0]["path"])
            except OSError as exc:
                self.h.close()
                self.h = None
                raise DeviceError(f"Could not open keypad RGB channel: {exc}") from exc
        # HID may have queued reports before opening. Drain both channels so
        # each command is matched to its own reply.
        for handle in (self.h, self.led_h):
            if handle is not None and hasattr(handle, "set_nonblocking"):
                handle.set_nonblocking(1)
                try:
                    while handle.read(64):
                        pass
                finally:
                    handle.set_nonblocking(0)
        return self

    def close(self):
        for handle in (self.h, self.led_h):
            if handle:
                try:
                    handle.close()
                except Exception:
                    pass

    def _xfer(self, cmd, payload=b""):
        self.h.write(sayo.frame(cmd, payload))
        deadline = time.monotonic() + 1.0
        unrelated = b""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                suffix = f"; last unrelated HID report: {unrelated[:16].hex(' ')}" if unrelated else ""
                raise DeviceError(f"No config reply to command {cmd:#04x}{suffix}")
            resp = bytes(self.h.read(64, max(1, int(remaining * 1000))))
            if len(resp) < 3:
                suffix = f"; last unrelated HID report: {unrelated[:16].hex(' ')}" if unrelated else ""
                raise DeviceError(f"No reply to command {cmd:#04x}{suffix}")
            if resp[0] == sayo.REPORT_ID:
                return resp
            unrelated = resp

    def identify(self):
        now = datetime.datetime.now()
        resp = self._xfer(
            CMD_IDENTIFY, bytes([now.day, now.hour, now.minute, now.second])
        )
        if resp[1] != 0:
            raise DeviceError("Keypad did not answer identify")
        return resp[3:3 + resp[2]]

    def read_key(self, n):
        """Return the key's full payload (with its leading pattern byte)."""
        if not 0 <= n < NUM_KEYS:
            raise ValueError(f"key number must be 0-{NUM_KEYS - 1}, got {n}")
        last_reply = b""
        for _ in range(NUM_KEYS):
            resp = self._xfer(CMD_KEY, bytes([0, n]))
            last_reply = resp
            if resp[1] != 0:
                raise DeviceError(f"Key {n} not readable (status {resp[1]:#04x})")
            payload = bytearray(resp[3:3 + resp[2]])
            if len(payload) < KEY_RECORD_SIZE:
                raise DeviceError(
                    f"Key {n} reply is too short ({len(payload)} bytes; "
                    f"expected {KEY_RECORD_SIZE}); reply: {resp[:16].hex(' ')}"
                )
            if payload[1] == n:
                time.sleep(0.02)
                return payload[:KEY_RECORD_SIZE]
            self._discard_pending()
            time.sleep(0.02)
        payload = last_reply[3:3 + last_reply[2]]
        got = payload[1] if len(payload) > 1 else "missing"
        raise DeviceError(f"Requested key {n}, but keypad replied with key {got}; "
                          f"reply: {last_reply[:16].hex(' ')}")

    def _discard_pending(self):
        """Drop queued reports before retrying after a stale key reply."""
        if not hasattr(self.h, "set_nonblocking"):
            return
        self.h.set_nonblocking(1)
        try:
            while self.h.read(64):
                pass
        finally:
            self.h.set_nonblocking(0)

    def write_combo(self, n, combo, record_length=None):
        """Set key n to a key combination (base layer), then verify by reading back."""
        if record_length is not None and record_length != KEY_RECORD_SIZE:
            raise DeviceError(
                f"Invalid key record length {record_length} for key {n}; "
                f"expected {KEY_RECORD_SIZE}"
            )

        if not 0 <= n < NUM_KEYS:
            raise ValueError(f"key number must be 0-{NUM_KEYS - 1}, got {n}")
        record = self.read_key(n)
        record[0] = 1                  # pattern: write
        record[V0], record[V1] = combo.mods, combo.key
        record[V0 + 2], record[V1 + 2] = 0, 0
        resp = self._xfer(CMD_KEY, bytes(record))
        if resp[1] != 0:
            raise DeviceError(f"Writing key {n} failed (status {resp[1]:#04x})")
        back = self.read_key(n)
        if (back[V0], back[V1]) != (combo.mods, combo.key):
            raise DeviceError(f"Verify failed on key {n}: wrote {combo}, read "
                              f"{Combo(back[V0], back[V1])}")

    @staticmethod
    def _sign_v2(packet):
        packet[2:4] = b"\x00\x00"
        checksum = sum(packet[i] | (packet[i + 1] << 8)
                       for i in range(0, 64, 2)) & 0xFFFF
        packet[2] = checksum & 0xFF
        packet[3] = (checksum >> 8) & 0xFF

    def _v2_xfer(self, packet):
        if self.led_h is None:
            raise DeviceError("This keypad exposes no HID v2 RGB channel (usage page 0xFF11).")
        written = self.led_h.write(bytes(packet))
        if written <= 0:
            raise DeviceError(f"RGB HID write failed (returned {written})")
        deadline = time.monotonic() + 1.0
        unrelated = b""
        expected_command, expected_index = packet[6], packet[7]
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = f"; last unrelated report: {unrelated[:16].hex(' ')}" if unrelated else ""
                raise DeviceError(f"Timed out waiting for RGB HID v2 reply{detail}")
            resp = bytes(self.led_h.read(64, max(1, int(remaining * 1000))))
            if not resp:
                continue
            if len(resp) < 8:
                detail = f"; last unrelated report: {unrelated[:16].hex(' ')}" if unrelated else ""
                raise DeviceError(f"Short RGB HID reply ({len(resp)} bytes){detail}")
            if resp[0] == V2_REPORT_ID:
                if len(resp) != 64:
                    unrelated = resp
                    continue
                # The FF00 and FF11 collections share a report queue on this
                # device. Match the V2 command and LED index too; report ID
                # alone can accept an older LED record as the current reply.
                if resp[6] == expected_command and resp[7] == expected_index:
                    return resp
            unrelated = resp

    def _read_led_record(self, n):
        packet = bytearray(64)
        packet[0:8] = bytes([V2_REPORT_ID, V2_COMMAND, 0, 0, 4, 0, V2_LIGHT, n])
        self._sign_v2(packet)
        resp = self._v2_xfer(packet)
        if resp[4] != 0x3C or resp[5] != 0 or resp[6] != V2_LIGHT or resp[7] != n:
            raise DeviceError(f"Invalid RGB read reply for LED {n}: {resp[:16].hex(' ')}")
        return bytearray(resp)

    def read_led(self, n):
        """Read LED RGB color for key index n (0..11)."""
        if not 0 <= n < NUM_KEYS:
            raise ValueError(f"LED number must be 0-{NUM_KEYS - 1}, got {n}")
        record = self._read_led_record(n)
        return tuple(record[28:31])

    def read_led_config(self, n):
        """Return an LED's RGB color, mode, and key-event behaviour."""
        if not 0 <= n < NUM_KEYS:
            raise ValueError(f"LED number must be 0-{NUM_KEYS - 1}, got {n}")
        record = self._read_led_record(n)
        return tuple(record[28:31]), record[24], record[25]

    def write_led(self, n, r, g, b, mode=LED_STATIC, event=LED_EVENT_NONE):
        """Set an LED's RGB color and optional key-event behaviour.

        Uses HID v2 Light records on usage page 0xFF11, preserving the rest of
        the LED record and signing the complete 64-byte report.
        """
        if not 0 <= n < NUM_KEYS:
            raise ValueError(f"LED number must be 0-{NUM_KEYS - 1}, got {n}")
        if any(not 0 <= c <= 255 for c in (r, g, b)):
            raise ValueError("LED RGB channels must be between 0 and 255")
        if not 0 <= mode <= 0xFF or not 0 <= event <= 0xFF:
            raise ValueError("LED mode and event must be between 0 and 255")
        record = self._read_led_record(n)
        record[0:8] = bytes([V2_REPORT_ID, V2_COMMAND, 0, 0, 0x3C, 0,
                             V2_LIGHT, n])
        record[24] = mode
        record[25] = event
        record[26] = 0x64
        record[27] = 0x64
        record[28:31] = bytes([r, g, b])
        record[31] = 0
        self._sign_v2(record)
        ack = self._v2_xfer(record)
        if ack[5] & 0x40 or ack[6] != V2_LIGHT or ack[7] != n:
            raise DeviceError(f"Writing LED for key {n + 1} failed; RGB v2 ACK: {ack[:16].hex(' ')}")
        actual = self.read_led(n)
        if actual != (r, g, b):
            raise DeviceError(f"LED verify failed on key {n + 1}: wrote {(r, g, b)}, read {actual}")
        self._led_dirty = True
        return actual

    def save_led(self):
        """Persist pending RGB changes using this keypad's working legacy save command."""
        if not self._led_dirty:
            return
        self.save()
        self._led_dirty = False

    def save(self):
        """Commit key and lighting configuration to device flash."""
        resp = self._xfer(CMD_SAVE, bytes([0x72, 0x96]))
        if resp[1] != 0:
            raise DeviceError("Save failed")

    def backup_all(self):
        return {n: self.read_key(n) for n in range(NUM_KEYS)}

    def restore_all(self, backup):
        for n, record in backup.items():
            self.write_combo(n, Combo(record[V0], record[V1]), len(record))
        self.save()
