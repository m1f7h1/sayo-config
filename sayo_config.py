"""Focused browser UI for reading and editing a SayoDevice 2×6V keypad."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import webbrowser


KEYBOARD_PROJECT = Path(__file__).resolve().parent.parent / "sayo-keyboard"
sys.path.insert(0, str(KEYBOARD_PROJECT))

import sayo  # noqa: E402


MOD_ORDER = ("ctrl", "shift", "alt", "cmd")
CODE_TO_NAME = {code: name for name, code in sayo.KEYS.items()}
PHYSICAL_MARKER_MODS = sum(sayo.MODIFIERS.values())
PHYSICAL_MARKERS = {
    sayo.KEYS[f"f{13 + n}"]: n + 1 for n in range(12)
}


def combo_name(combo):
    parts = [name for name in MOD_ORDER if combo.mods & sayo.MODIFIERS[name]]
    parts.append(CODE_TO_NAME.get(combo.key, f"key-{combo.key:02x}"))
    return "+".join(parts)


def combo_from_event(data):
    """Convert a browser physical key code and its modifiers to a Sayo combo."""
    code = data.get("code", "")
    name = None
    if code.startswith("Key") and len(code) == 4:
        name = code[-1].lower()
    elif code.startswith("Digit") and code[-1:].isdigit():
        name = code[-1]
    elif code.startswith("Numpad") and code[-1:].isdigit():
        name = code[-1]
    elif code.startswith("F") and code[1:].isdigit():
        name = code.lower()
    else:
        name = {
            "Enter": "enter", "Escape": "esc", "Backspace": "backspace",
            "Tab": "tab", "Space": "space", "Minus": "-", "Equal": "=",
            "BracketLeft": "[", "BracketRight": "]", "Backslash": "\\",
            "Semicolon": ";", "Quote": "'", "Backquote": "`", "Comma": ",",
            "Period": ".", "Slash": "/", "Home": "home", "PageUp": "pageup",
            "Delete": "delete", "End": "end", "PageDown": "pagedown",
            "ArrowRight": "right", "ArrowLeft": "left", "ArrowDown": "down",
            "ArrowUp": "up",
        }.get(code)
    if name not in sayo.KEYS:
        return None
    mods = 0
    for field, modifier in (("ctrl", "ctrl"), ("shift", "shift"),
                            ("alt", "alt"), ("cmd", "cmd")):
        if data.get(field):
            mods |= sayo.MODIFIERS[modifier]
    return sayo.Combo(mods, sayo.KEYS[name])


def key_svg(number):
    return f"""\
<svg class="key" viewBox="0 0 132 124" role="img" aria-label="Key {number}"
     data-key="{number}" tabindex="0">
  <title>Key {number}</title>
  <path d="M18 21 Q18 13 27 13 H105 Q114 13 114 22 V101 Q114 109 105 109 H27 Q18 109 18 101 Z"
        fill="#d8dde5"/>
  <path d="M14 16 Q14 8 23 8 H101 Q110 8 110 17 V94 Q110 102 101 102 H23 Q14 102 14 94 Z"
        fill="#c8ced7" stroke="#b8c0cb" stroke-width="1.5"/>
  <path d="M19 15 Q19 12 24 12 H99 Q105 12 105 18 V83 H19 Z"
        fill="#fff" stroke="#e3e7ed" stroke-width="1.5"/>
  <text x="62" y="48" text-anchor="middle" aria-label="No binding">—</text>
</svg>"""


def page_html():
    keys = "\n".join(key_svg(number) for number in range(1, 13))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sayo Key Grid</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; }}
    body {{
      display: grid; place-items: center; min-height: 100vh;
      background: #f2f4f7; color: #263244;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    main {{ padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(6, 124px); gap: 12px; }}
    .key {{ display: block; width: 124px; height: 116px; overflow: visible; cursor: pointer; outline: none; }}
    .key text {{ fill: #111; font-size: 11px; font-weight: 650; letter-spacing: .01em; }}
    .key.active path:nth-of-type(2) {{ stroke: #d32f36; stroke-width: 3; }}
    #status {{ margin: 16px 0 0; min-height: 20px; text-align: center; font-size: 13px; color: #566273; }}
    @media (max-width: 850px) {{
      body {{ display: block; }} main {{ padding: 16px 12px; }}
      .grid {{ grid-template-columns: repeat(3, minmax(76px, 124px)); justify-content: center; gap: 8px; }}
      .key {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main aria-label="SayoDevice 2 by 6 key grid">
    <div class="grid">{keys}</div>
    <p id="status" role="status">Connecting to the keypad…</p>
  </main>
  <script>
    const statusLine = document.querySelector('#status');
    let state = {{ bindings: {{}}, active: null, pending: null }};
    let chordHasKey = false;

    function wrapLabel(label) {{
      if (!label || label === '—') return ['—'];
      const parts = label.split('+');
      const lines = [];
      let line = '';
      for (const part of parts) {{
        const next = line ? line + '+' + part : part;
        if (next.length > 15 && line) {{ lines.push(line + '+'); line = part; }}
        else line = next;
      }}
      if (line) lines.push(line);
      return lines.slice(0, 3);
    }}

    function draw() {{
      document.querySelectorAll('.key').forEach(svg => {{
        const n = Number(svg.dataset.key);
        const active = state.active === n;
        svg.classList.toggle('active', active);
        const label = state.pending && active ? state.pending : (state.bindings[n] || '—');
        const text = svg.querySelector('text');
        text.replaceChildren();
        const lines = wrapLabel(label);
        const start = lines.length === 1 ? 48 : (lines.length === 2 ? 43 : 38);
        lines.forEach((line, i) => {{
          const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tspan.setAttribute('x', '62'); tspan.setAttribute('y', String(start + i * 13));
          tspan.textContent = line; text.appendChild(tspan);
        }});
        svg.setAttribute('aria-label', `Key ${{n}}: ${{label}}${{active ? ', active' : ''}}`);
      }});
      if (state.error) statusLine.textContent = state.error;
      else if (state.active !== null) {{
        const instruction = state.pending
          ? `Key ${{state.active}}: previewing ${{state.pending}}. Press another shortcut to replace it; click this key to save or another key to discard.`
          : `Key ${{state.active}} active. Press a shortcut, then click this key to save or another key to discard.`;
        statusLine.textContent = state.warning ? `${{instruction}} ${{state.warning}}` : instruction;
      }} else if (state.ready) statusLine.textContent = state.warning || 'Click a key or press a uniquely mapped key on the keypad.';
      else statusLine.textContent = state.message || 'Connecting to the keypad…';
    }}

    async function api(path, body) {{
      const response = await fetch(path, {{
        method: body ? 'POST' : 'GET',
        headers: body ? {{ 'Content-Type': 'application/json' }} : {{}},
        body: body ? JSON.stringify(body) : undefined,
      }});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Request failed');
      return result;
    }}

    async function refresh() {{
      try {{ state = await api('/api/state'); }}
      catch (error) {{ state.error = error.message; }}
      draw();
    }}

    document.querySelectorAll('.key').forEach(svg => {{
      const select = async () => {{
        try {{ state = await api('/api/select', {{ key: Number(svg.dataset.key) }}); }}
        catch (error) {{ state.error = error.message; }}
        draw();
      }};
      svg.addEventListener('click', select);
      svg.addEventListener('keydown', event => {{
        if (event.key === 'Enter' || event.key === ' ') {{ event.preventDefault(); select(); }}
      }});
    }});

    window.addEventListener('keydown', async event => {{
      if (event.repeat || event.isComposing) return;
      const isModifier = ['ShiftLeft','ShiftRight','ControlLeft','ControlRight',
        'AltLeft','AltRight','MetaLeft','MetaRight'].includes(event.code);
      if (isModifier || !state.ready) return;
      event.preventDefault();
      if (chordHasKey) return;
      chordHasKey = true;
      const keyData = {{ code: event.code, ctrl: event.ctrlKey, shift: event.shiftKey,
        alt: event.altKey, cmd: event.metaKey }};
      try {{
        const result = await api('/api/key', keyData);
        state = result;
        draw();
        if (result.active !== null || result.matched) event.preventDefault();
      }} catch (error) {{ state.error = error.message; draw(); }}
    }});
    window.addEventListener('keyup', event => {{
      if (!['ShiftLeft','ShiftRight','ControlLeft','ControlRight','AltLeft','AltRight','MetaLeft','MetaRight'].includes(event.code))
        chordHasKey = false;
    }});
    window.addEventListener('focus', refresh);
    refresh();
    window.focus();
  </script>
</body>
</html>"""


class App:
    def __init__(self):
        self.device = None
        self.device_module = None
        self.bindings = {}
        self.saved_records = {}
        self.markers_installed = False
        self.warning = None
        self.active = None
        self.pending = None
        self.error = None
        self.ready = False
        self.message = "Opening keypad…"
        self.connect()

    def connect(self):
        try:
            import device as device_module
            self.device_module = device_module
            self.device = device_module.Device().open()
            self.device.identify()
            for n in range(12):
                payload = self.device.read_key(n)
                self.saved_records[n] = bytes(payload)
                code, mods = payload[device_module.V1], payload[device_module.V0]
                if code:
                    self.bindings[n + 1] = combo_name(sayo.Combo(mods, code))
            self.install_physical_markers()
            self.ready = True
            self.message = ""
        except Exception as exc:
            if self.device is not None and self.saved_records:
                try:
                    self.restore_saved_records()
                except Exception:
                    pass
            self.error = f"Could not read the keypad: {exc}"
            self.message = self.error

    def restore_saved_records(self):
        """Put the last committed 12 key records into device RAM."""
        for n, record in self.saved_records.items():
            payload = bytearray(record)
            payload[0] = 1
            response = self.device._xfer(self.device_module.CMD_KEY, bytes(payload))
            if response[1] != 0:
                raise RuntimeError(f"Could not restore physical key {n + 1}.")
            check = self.device.read_key(n)
            if bytes(check[1:]) != bytes(payload[1:]):
                raise RuntimeError(f"Could not verify physical key {n + 1} restore.")

    def install_physical_markers(self):
        """Give every physical key a distinct temporary browser-visible chord."""
        for n in range(12):
            self.device.write_combo(
                n, sayo.Combo(PHYSICAL_MARKER_MODS, sayo.KEYS[f"f{13 + n}"])
            )
        self.markers_installed = True

    def persist_pending(self, key_number):
        """Commit one edited binding while keeping physical keys identifiable."""
        self.restore_saved_records()
        if self.pending:
            combo = sayo.parse_combo(self.pending)
            self.device.write_combo(key_number - 1, combo)
            self.device.save()
            self.saved_records[key_number - 1] = bytes(self.device.read_key(key_number - 1))
            self.bindings[key_number] = self.pending
        self.install_physical_markers()

    def state(self, **extra):
        result = {"bindings": self.bindings, "active": self.active,
                  "pending": self.pending, "ready": self.ready,
                  "error": self.error, "message": self.message,
                  "warning": self.warning}
        result.update(extra)
        return result

    def toggle_key(self, n):
        """Apply the same toggle/switch rules for virtual and physical keys."""
        if not self.ready:
            raise RuntimeError(self.error or "The keypad is not connected.")
        if n == self.active:
            # Same key again: persist its pending mapping and turn it off.
            if self.pending:
                self.persist_pending(n)
            self.active = None
            self.pending = None
        else:
            # Different key: discard the old preview and switch selection.
            self.active = n
            self.pending = None
        self.error = None
        return self.state()

    def select(self, n):
        # Kept as the HTTP handler entry point; all inputs share toggle_key.
        return self.toggle_key(n)

    def key_event(self, data):
        combo = combo_from_event(data)
        if combo is None:
            return self.state()
        label = combo_name(combo)
        if combo.mods == PHYSICAL_MARKER_MODS and combo.key in PHYSICAL_MARKERS:
            self.toggle_key(PHYSICAL_MARKERS[combo.key])
            return self.state(matched=True, physical=True)
        if self.active is None:
            # Ordinary Mac key presses must never select a pad key just
            # because their shortcut happens to match its saved binding.
            return self.state(matched=False)
        # While a key is active, every keyboard event is a candidate new
        # binding. Do not mistake a captured digit/shortcut for another mapped
        # keypad key or toggle the active key off.
        self.pending = label
        self.error = None
        return self.state(matched=True)

    def close(self):
        if self.device is not None and self.markers_installed:
            try:
                self.restore_saved_records()
            except Exception:
                pass
        if self.device is not None:
            self.device.close()


app = None


class Handler(BaseHTTPRequestHandler):
    def respond(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/state":
            self.respond(app.state())
            return
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = page_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length))
            if self.path == "/api/select":
                n = int(data["key"])
                if not 1 <= n <= 12:
                    raise ValueError("Key number must be between 1 and 12.")
                self.respond(app.select(n))
            elif self.path == "/api/key":
                self.respond(app.key_event(data))
            else:
                self.send_error(404)
        except Exception as exc:
            app.error = str(exc)
            self.respond(app.state(), status=500)

    def log_message(self, _format, *_args):
        pass


def main():
    global app
    app = App()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    webbrowser.open(url, new=1, autoraise=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
