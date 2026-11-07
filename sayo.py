"""sayo.py - a minimal configurator for the SayoDevice 2x6V keypad.

Protocol reference: SayoDevice's own MIT-licensed Sayo_CLI (github.com/Sayobot/Sayo_CLI, o2_protocol.cpp).
This is a fresh implementation of only the messages we need; no code was copied.
"""

from typing import NamedTuple

REPORT_ID = 0x02     # every config message uses HID report 2
FRAME_SIZE = 64      # messages are always 64 bytes, zero padded
MAX_PAYLOAD = 60     # 64 - report id - command - length byte - checksum


def frame(cmd, payload=b""):
    """Build one 64-byte message: [report id, command, payload length, payload..., checksum, zero padding].
    The checksum is the low byte of the sum of everything before it."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload is {len(payload)} bytes; the most a message can carry is {MAX_PAYLOAD}")
    body = bytes([REPORT_ID, cmd, len(payload)]) + bytes(payload)
    body += bytes([sum(body) & 0xFF])
    return body + bytes(FRAME_SIZE - len(body))


# ---------------------------------------------------------------------------
# Settings file: what each key should do
# ---------------------------------------------------------------------------

NUM_KEYS = 12
MAX_TEXT = 57   # one message holds mode, slot, the text and a terminating zero: 60 - 3

class Combo(NamedTuple):
    mods: int   # modifier bits, see MODIFIERS
    key: int    # USB HID keyboard usage code

class Text(NamedTuple):
    text: str

class Mac(NamedTuple):
    label: str  # only used in the setup instructions we print

class SettingsError(ValueError):
    pass

# Standard USB HID modifier bits (same as every USB keyboard). On a Mac, "GUI" is the Cmd key.
MODIFIERS = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "cmd": 0x08}

# USB HID keyboard usage codes (USB HID Usage Tables, Keyboard/Keypad page 0x07).
KEYS = {chr(ord("a") + i): 0x04 + i for i in range(26)}               # a..z
KEYS.update({str(d): 0x1E + d - 1 for d in range(1, 10)})              # 1..9
KEYS["0"] = 0x27
KEYS.update({f"f{n}": 0x3A + n - 1 for n in range(1, 13)})             # F1..F12
KEYS.update({f"f{n}": 0x68 + n - 13 for n in range(13, 25)})           # F13..F24
KEYS.update({
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34,
    "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
    "home": 0x4A, "pageup": 0x4B, "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
})


def parse_combo(spec):
    """'cmd+shift+4' -> Combo. Any number of modifiers, exactly one normal key."""
    mods, key = 0, None
    for part in (p.strip().lower() for p in spec.split("+")):
        if part in MODIFIERS:
            if mods & MODIFIERS[part]:
                raise ValueError(f"'{part}' appears twice in '{spec}'")
            mods |= MODIFIERS[part]
        elif part in KEYS:
            if key is not None:
                raise ValueError(f"'{spec}' has more than one normal key")
            key = KEYS[part]
        else:
            raise ValueError(f"unknown key '{part}' in '{spec}'")
    if key is None:
        raise ValueError(f"'{spec}' needs one normal key (modifiers alone are not supported)")
    return Combo(mods, key)


def parse_settings(text):
    """Read the settings file. Returns {key number: Combo | Text | Mac}.
    Lines are 'N = action'; whole-line comments start with '#'."""
    actions = {}
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            number, sep, action = line.partition("=")
            if not sep or not number.strip().isdigit():
                raise ValueError("expected 'key number = action'")
            number = int(number)
            if not 1 <= number <= NUM_KEYS:
                raise ValueError(f"key number must be 1-{NUM_KEYS}, got {number}")
            if number in actions:
                raise ValueError(f"key {number} is set more than once")
            actions[number] = _parse_action(action.strip())
        except ValueError as e:
            raise SettingsError(f"line {line_no}: {e}") from None
    return actions


def _parse_action(action):
    kind, _, rest = action.partition(":")
    kind, rest = kind.strip().lower(), rest.strip()
    if kind == "text":
        if not rest:
            raise ValueError("text is empty")
        # The pad types by key position and only knows plain ASCII.
        if any(not (0x20 <= ord(c) <= 0x7E) for c in rest):
            raise ValueError("text can only use plain ASCII characters (no £, accents, emoji...)")
        if len(rest) > MAX_TEXT:
            raise ValueError(f"text is {len(rest)} characters; the limit is {MAX_TEXT}")
        return Text(rest)
    if kind == "mac":
        if not rest:
            raise ValueError("Mac action needs a label, e.g. 'mac: Hide all apps'")
        return Mac(rest)
    return parse_combo(action)
