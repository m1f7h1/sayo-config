"""Focused browser UI for reading and editing a SayoDevice 2×6V keypad."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import importlib.util
from pathlib import Path
import sys
import webbrowser

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

# Ensure device.py is loaded directly from this exact directory
device_path = PROJECT_DIR / "device.py"
spec = importlib.util.spec_from_file_location("device", device_path)
device_module = importlib.util.module_from_spec(spec)
sys.modules["device"] = device_module
spec.loader.exec_module(device_module)

import sayo


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
  <text x="62" y="44" text-anchor="middle" aria-label="No binding">—</text>
  <rect class="led-bar" x="44" y="66" width="36" height="6" rx="3"
        fill="#ffffff" stroke="#c0c7d2" stroke-width="1"/>
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
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    main {{
      padding: 24px; display: flex; flex-direction: column;
      align-items: center; max-width: 860px;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(6, 124px); gap: 12px; }}
    .key {{ display: block; width: 124px; height: 116px; overflow: visible; cursor: pointer; outline: none; }}
    .key text {{ fill: #111; font-size: 11px; font-weight: 650; letter-spacing: .01em; }}
    .key.active path:nth-of-type(2) {{ stroke: #d32f36; stroke-width: 3; }}
    .key .led-bar {{ transition: fill 0.15s ease, filter 0.15s ease; }}

    #color-panel {{
      margin-top: 20px;
      padding: 16px 20px;
      background: #ffffff;
      border: 1px solid #dcdfe4;
      border-radius: 12px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.06);
      display: none;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }}
    #color-panel.visible {{ display: flex; }}
    .color-panel-header {{
      display: flex; justify-content: space-between; align-items: center;
      width: 100%; font-size: 13px; font-weight: 600; color: #374151;
    }}
    .color-panel-body {{
      display: flex; gap: 20px; align-items: center;
    }}
    .wheel-wrap {{
      position: relative; width: 140px; height: 140px;
      cursor: crosshair; user-select: none;
    }}
    #wheel-canvas {{ border-radius: 50%; box-shadow: inset 0 0 1px rgba(0,0,0,0.3); }}
    .wheel-cursor {{
      position: absolute; width: 12px; height: 12px;
      border: 2px solid #ffffff; border-radius: 50%;
      box-shadow: 0 0 3px rgba(0,0,0,0.7);
      transform: translate(-50%, -50%);
      pointer-events: none;
    }}
    .color-controls {{
      display: flex; flex-direction: column; gap: 10px; width: 170px;
    }}
    .slider-row {{
      display: flex; flex-direction: column; gap: 4px;
      font-size: 11px; color: #6b7280; font-weight: 500;
    }}
    .slider-row input[type="range"] {{
      width: 100%; accent-color: #2563eb; cursor: pointer;
    }}
    .preview-row {{
      display: flex; align-items: center; gap: 8px;
    }}
    .color-chip {{
      width: 30px; height: 30px; border-radius: 6px;
      border: 1px solid #d1d5db; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      cursor: pointer; position: relative;
    }}
    #native-color {{
      position: absolute; opacity: 0; width: 100%; height: 100%;
      top: 0; left: 0; cursor: pointer;
    }}
    #hex-input {{
      font-family: ui-monospace, Menlo, monospace;
      font-size: 13px; font-weight: 600; text-transform: uppercase;
      padding: 5px 8px; width: 85px; border-radius: 6px;
      border: 1px solid #cbd5e1; color: #1e293b; background: #f8fafc;
    }}
    .swatches {{
      display: flex; flex-wrap: wrap; gap: 6px; max-width: 170px;
    }}
    .swatch {{
      width: 18px; height: 18px; border-radius: 4px;
      border: 1px solid rgba(0,0,0,0.15); cursor: pointer;
      transition: transform 0.1s ease;
    }}
    .swatch:hover {{ transform: scale(1.18); }}

    #status {{
      margin: 18px 0 0; min-height: 20px; text-align: center;
      font-size: 13px; color: #566273; max-width: 600px;
    }}
    @media (max-width: 850px) {{
      body {{ display: block; }} main {{ padding: 16px 12px; }}
      .grid {{ grid-template-columns: repeat(3, minmax(76px, 124px)); justify-content: center; gap: 8px; }}
      .key {{ width: 100%; }}
      .color-panel-body {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main aria-label="SayoDevice 2 by 6 key grid">
    <div class="grid">{keys}</div>

    <!-- Color Wheel / LED Configurator Panel -->
    <div id="color-panel">
      <div class="color-panel-header">
        <span id="color-panel-title">Active Key LED Color</span>
        <span id="color-panel-note" style="font-weight:normal; font-size:11px; color:#6b7280;">Saves with key</span>
      </div>
      <div class="color-panel-body">
        <div class="wheel-wrap" id="wheel-wrap">
          <canvas id="wheel-canvas" width="140" height="140"></canvas>
          <div class="wheel-cursor" id="wheel-cursor"></div>
        </div>
        <div class="color-controls">
          <div class="preview-row">
            <div class="color-chip" id="color-chip" title="Click for native color picker">
              <input type="color" id="native-color">
            </div>
            <input type="text" id="hex-input" maxlength="7" spellcheck="false" value="#FFFFFF">
          </div>
          <div class="slider-row">
            <label for="val-slider">Brightness</label>
            <input type="range" id="val-slider" min="0" max="100" value="100">
          </div>
          <label class="slider-row" style="justify-content:flex-start; gap:8px;">
            <input type="checkbox" id="press-lighting">
            Light only while this key is pressed
          </label>
          <div class="swatches" id="swatches"></div>
        </div>
      </div>
    </div>

    <p id="status" role="status">Connecting to the keypad…</p>
  </main>
  <script>
    const statusLine = document.querySelector('#status');
    const colorPanel = document.querySelector('#color-panel');
    const colorPanelTitle = document.querySelector('#color-panel-title');
    const wheelCanvas = document.querySelector('#wheel-canvas');
    const wheelWrap = document.querySelector('#wheel-wrap');
    const wheelCursor = document.querySelector('#wheel-cursor');
    const valSlider = document.querySelector('#val-slider');
    const colorChip = document.querySelector('#color-chip');
    const nativeColor = document.querySelector('#native-color');
    const hexInput = document.querySelector('#hex-input');
    const pressLighting = document.querySelector('#press-lighting');
    const swatchesContainer = document.querySelector('#swatches');

    const PRESET_COLORS = [
      '#FF0000', '#FF7F00', '#FFFF00', '#00FF00',
      '#00FFFF', '#0070FF', '#9B00FF', '#FF007F',
      '#FFFFFF', '#FFE2A0', '#000000'
    ];

    PRESET_COLORS.forEach(hex => {{
      const b = document.createElement('div');
      b.className = 'swatch';
      b.style.backgroundColor = hex;
      b.title = hex;
      b.addEventListener('click', () => setColorFromHex(hex, true));
      swatchesContainer.appendChild(b);
    }});

    let state = {{ bindings: {{}}, colors: {{}}, press_lighting: {{}}, active: null, pending: null, pending_color: null, pending_press_lighting: null }};
    let chordHasKey = false;
    let currentHSV = {{ h: 0, s: 0, v: 1 }};
    let isDraggingWheel = false;

    // --- Color Math Helpers ---
    function hsvToRgb(h, s, v) {{
      const c = v * s;
      const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
      const m = v - c;
      let r = 0, g = 0, b = 0;
      if (h < 60) {{ r = c; g = x; }}
      else if (h < 120) {{ r = x; g = c; }}
      else if (h < 180) {{ g = c; b = x; }}
      else if (h < 240) {{ g = x; b = c; }}
      else if (h < 300) {{ r = x; b = c; }}
      else {{ r = c; b = x; }}
      return [
        Math.round((r + m) * 255),
        Math.round((g + m) * 255),
        Math.round((b + m) * 255)
      ];
    }}

    function rgbToHsv(r, g, b) {{
      r /= 255; g /= 255; b /= 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      const d = max - min;
      let h = 0;
      const s = max === 0 ? 0 : d / max;
      const v = max;
      if (d !== 0) {{
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
        else if (max === g) h = ((b - r) / d + 2) * 60;
        else h = ((r - g) / d + 4) * 60;
      }}
      return {{ h, s, v }};
    }}

    function rgbToHex(r, g, b) {{
      return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('').toUpperCase();
    }}

    function hexToRgb(hex) {{
      hex = hex.replace('#', '');
      if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
      if (hex.length !== 6) return [255, 255, 255];
      const num = parseInt(hex, 16);
      return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
    }}

    function drawWheel() {{
      const ctx = wheelCanvas.getContext('2d');
      const w = wheelCanvas.width;
      const h = wheelCanvas.height;
      const cx = w / 2;
      const cy = h / 2;
      const radius = cx - 2;
      const img = ctx.createImageData(w, h);
      const data = img.data;

      for (let y = 0; y < h; y++) {{
        for (let x = 0; x < w; x++) {{
          const dx = x - cx;
          const dy = y - cy;
          const dist = Math.hypot(dx, dy);
          const idx = (y * w + x) * 4;
          if (dist <= radius) {{
            let angle = Math.atan2(dy, dx) * 180 / Math.PI;
            if (angle < 0) angle += 360;
            const sat = Math.min(1, dist / radius);
            const [r, g, b] = hsvToRgb(angle, sat, currentHSV.v);
            data[idx] = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            data[idx + 3] = 255;
          }} else {{
            data[idx + 3] = 0;
          }}
        }}
      }}
      ctx.putImageData(img, 0, 0);

      // Update Cursor position
      const rad = (currentHSV.h * Math.PI) / 180;
      const d = currentHSV.s * radius;
      const mx = cx + d * Math.cos(rad);
      const my = cy + d * Math.sin(rad);
      wheelCursor.style.left = `${{mx}}px`;
      wheelCursor.style.top = `${{my}}px`;
      wheelCursor.style.borderColor = currentHSV.v > 0.5 && currentHSV.s < 0.4 ? '#333' : '#fff';
    }}

    function updateColorUI(hex) {{
      colorChip.style.backgroundColor = hex;
      nativeColor.value = hex;
      hexInput.value = hex;
      valSlider.value = Math.round(currentHSV.v * 100);
      drawWheel();
    }}

    async function sendColor(hex) {{
      if (state.active === null) return;
      state.pending_color = hex;
      draw();
      try {{
        const res = await api('/api/color', {{ key: state.active, color: hex }});
        state = res;
        draw();
      }} catch (err) {{
        state.error = err.message;
        draw();
      }}
    }}

    async function setPressLighting(enabled) {{
      if (state.active === null) return;
      state.pending_press_lighting = enabled;
      draw();
      try {{
        state = await api('/api/press-lighting', {{ key: state.active, enabled }});
        draw();
      }} catch (err) {{
        state.error = err.message;
        draw();
      }}
    }}

    function setColorFromHex(hex, send = true) {{
      const [r, g, b] = hexToRgb(hex);
      currentHSV = rgbToHsv(r, g, b);
      const standardHex = rgbToHex(r, g, b);
      updateColorUI(standardHex);
      if (send) sendColor(standardHex);
    }}

    function pickFromWheelEvent(e) {{
      const rect = wheelCanvas.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const x = (e.clientX || (e.touches && e.touches[0].clientX)) - rect.left - cx;
      const y = (e.clientY || (e.touches && e.touches[0].clientY)) - rect.top - cy;
      const radius = cx - 2;
      let angle = Math.atan2(y, x) * 180 / Math.PI;
      if (angle < 0) angle += 360;
      const dist = Math.hypot(x, y);
      const sat = Math.min(1, dist / radius);
      currentHSV.h = angle;
      currentHSV.s = sat;
      const [r, g, b] = hsvToRgb(currentHSV.h, currentHSV.s, currentHSV.v);
      const hex = rgbToHex(r, g, b);
      updateColorUI(hex);
      sendColor(hex);
    }}

    wheelWrap.addEventListener('mousedown', e => {{
      isDraggingWheel = true;
      pickFromWheelEvent(e);
    }});
    window.addEventListener('mousemove', e => {{
      if (isDraggingWheel) pickFromWheelEvent(e);
    }});
    window.addEventListener('mouseup', () => {{
      isDraggingWheel = false;
    }});

    valSlider.addEventListener('input', () => {{
      currentHSV.v = valSlider.value / 100;
      const [r, g, b] = hsvToRgb(currentHSV.h, currentHSV.s, currentHSV.v);
      const hex = rgbToHex(r, g, b);
      updateColorUI(hex);
      sendColor(hex);
    }});

    hexInput.addEventListener('change', () => {{
      let val = hexInput.value.trim();
      if (!val.startsWith('#')) val = '#' + val;
      if (/^#[0-9A-Fa-f]{{6}}$/.test(val)) {{
        setColorFromHex(val, true);
      }} else {{
        const [r, g, b] = hsvToRgb(currentHSV.h, currentHSV.s, currentHSV.v);
        hexInput.value = rgbToHex(r, g, b);
      }}
    }});

    nativeColor.addEventListener('input', e => {{
      setColorFromHex(e.target.value, true);
    }});
    pressLighting.addEventListener('change', e => setPressLighting(e.target.checked));

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
        const start = lines.length === 1 ? 44 : (lines.length === 2 ? 39 : 34);
        lines.forEach((line, i) => {{
          const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tspan.setAttribute('x', '62'); tspan.setAttribute('y', String(start + i * 13));
          tspan.textContent = line; text.appendChild(tspan);
        }});

        // Update Key LED Indicator
        const ledBar = svg.querySelector('.led-bar');
        if (ledBar) {{
          const col = (active && state.pending_color)
            ? state.pending_color
            : (state.colors[n] || '#FFFFFF');
          ledBar.setAttribute('fill', col);
          if (col === '#000000') {{
            ledBar.style.filter = 'none';
            ledBar.setAttribute('fill', '#262d38');
          }} else {{
            ledBar.style.filter = `drop-shadow(0 0 3px ${{col}})`;
          }}
        }}

        svg.setAttribute('aria-label', `Key ${{n}}: ${{label}}${{active ? ', active' : ''}}`);
      }});

      // Color panel visibility and state
      if (state.active !== null) {{
        colorPanel.classList.add('visible');
        colorPanelTitle.textContent = `Key ${{state.active}} LED Color`;
        const activeColor = state.pending_color || state.colors[state.active] || '#FFFFFF';
        const [r, g, b] = hexToRgb(activeColor);
        currentHSV = rgbToHsv(r, g, b);
        updateColorUI(rgbToHex(r, g, b));
        pressLighting.checked = state.pending_press_lighting ?? Boolean(state.press_lighting[state.active]);
      }} else {{
        colorPanel.classList.remove('visible');
      }}

      if (state.error) statusLine.textContent = state.error;
      else if (state.active !== null) {{
        let parts = [];
        if (state.pending) parts.push(`shortcut '${{state.pending}}'`);
        if (state.pending_color) parts.push(`color ${{state.pending_color}}`);
        if (state.pending_press_lighting !== null) parts.push(state.pending_press_lighting ? 'press-only lighting' : 'always-on lighting');
        const previewText = parts.length > 0 ? parts.join(' and ') : 'shortcut/color';
        const instruction = (state.pending || state.pending_color || state.pending_press_lighting !== null)
          ? `Key ${{state.active}}: previewing ${{previewText}}. Click this key to save or another key to discard.`
          : `Key ${{state.active}} active. Press a shortcut or pick a color, then click this key to save or another to discard.`;
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
      // Do not intercept input when typing inside an input element like hex-input
      if (event.target.tagName === 'INPUT') return;
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
        self.colors = {n: "#FFFFFF" for n in range(1, 13)}
        self.press_lighting = {n: False for n in range(1, 13)}
        self.saved_records = {}
        self.markers_installed = False
        self.warning = None
        self.active = None
        self.pending = None
        self.pending_color = None
        self.pending_press_lighting = None
        self.error = None
        self.ready = False
        self.message = "Opening keypad…"
        self.connect()

    def connect(self):
        try:
            self.device_module = device_module
            self.device = device_module.Device().open()
            self.device.identify()
            for n in range(12):
                payload = self.device.read_key(n)
                self.saved_records[n] = bytes(payload)
                code, mods = payload[device_module.V1], payload[device_module.V0]
                if code:
                    self.bindings[n + 1] = combo_name(sayo.Combo(mods, code))
                try:
                    if hasattr(self.device, "read_led_config"):
                        led_rgb, _mode, event = self.device.read_led_config(n)
                        if led_rgb is not None:
                            self.colors[n + 1] = f"#{led_rgb[0]:02X}{led_rgb[1]:02X}{led_rgb[2]:02X}"
                            self.press_lighting[n + 1] = event == device_module.LED_EVENT_PRESS_ON_RELEASE_OFF
                except Exception:
                    pass
            self.install_physical_markers()
            self.ready = True
            self.error = None
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
        """Restore the last committed key bindings into device RAM."""
        v0, v1 = self.device_module.V0, self.device_module.V1
        for n, record in self.saved_records.items():
            try:
                self.device.write_combo(
                    n, sayo.Combo(record[v0], record[v1]), record_length=len(record)
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Could not restore physical key {n + 1} "
                    f"({record[v0]:#04x}/{record[v1]:#04x}): {exc}"
                ) from exc

    def install_physical_markers(self):
        """Give every physical key a distinct temporary browser-visible chord."""
        for n in range(12):
            record = self.saved_records.get(n)
            self.device.write_combo(
                n, sayo.Combo(PHYSICAL_MARKER_MODS, sayo.KEYS[f"f{13 + n}"]),
                record_length=len(record) if record is not None else None,
            )
        self.markers_installed = True

    def persist_pending(self, key_number):
        """Commit one edited binding and/or LED color while keeping physical keys identifiable."""
        self.restore_saved_records()
        if self.pending:
            combo = sayo.parse_combo(self.pending)
            index = key_number - 1
            self.device.write_combo(
                index, combo, record_length=len(self.saved_records[index])
            )
            record = bytearray(self.saved_records[index])
            record[0] = 0
            record[self.device_module.V0] = combo.mods
            record[self.device_module.V1] = combo.key
            record[self.device_module.V0 + 2] = 0
            record[self.device_module.V1 + 2] = 0
            self.saved_records[index] = bytes(record)
            self.bindings[key_number] = self.pending
        if self.pending_color or self.pending_press_lighting is not None:
            color = self.pending_color or self.colors[key_number]
            c = color.lstrip("#")
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            press_only = (self.pending_press_lighting if self.pending_press_lighting is not None
                          else self.press_lighting[key_number])
            event = (self.device_module.LED_EVENT_PRESS_ON_RELEASE_OFF if press_only
                     else self.device_module.LED_EVENT_NONE)
            actual = self.device.write_led(key_number - 1, r, g, b, event=event)
            self.colors[key_number] = "#%02X%02X%02X" % actual
            self.press_lighting[key_number] = press_only
        if self.pending_color or self.pending_press_lighting is not None:
            self.device.save_led()
        elif self.pending:
            self.device.save()
        self.install_physical_markers()

    def set_color(self, n, hex_color):
        """Update active key's preview LED color."""
        if not self.ready:
            raise RuntimeError(self.error or "The keypad is not connected.")
        if self.active != n:
            self.active = n
            self.pending = None
            self.pending_press_lighting = None
        self.pending_color = hex_color.upper()
        # Preview on the hardware and surface any HID/write-back failure.
        c = self.pending_color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        press_only = (self.pending_press_lighting if self.pending_press_lighting is not None
                      else self.press_lighting[n])
        event = (self.device_module.LED_EVENT_PRESS_ON_RELEASE_OFF if press_only
                 else self.device_module.LED_EVENT_NONE)
        actual = self.device.write_led(n - 1, r, g, b, event=event)
        self.pending_color = "#%02X%02X%02X" % actual
        return self.state()

    def set_press_lighting(self, n, enabled):
        """Preview whether the active key lights only while held down."""
        if not self.ready:
            raise RuntimeError(self.error or "The keypad is not connected.")
        if self.active != n:
            self.active = n
            self.pending = None
            self.pending_color = None
        self.pending_press_lighting = bool(enabled)
        color = self.pending_color or self.colors[n]
        c = color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        event = (self.device_module.LED_EVENT_PRESS_ON_RELEASE_OFF if enabled
                 else self.device_module.LED_EVENT_NONE)
        actual = self.device.write_led(n - 1, r, g, b, event=event)
        self.pending_color = "#%02X%02X%02X" % actual
        return self.state()

    def state(self, **extra):
        if not self.ready:
            self.connect()
        result = {"bindings": self.bindings, "colors": self.colors,
                  "press_lighting": self.press_lighting,
                  "active": self.active, "pending": self.pending,
                  "pending_color": self.pending_color,
                  "pending_press_lighting": self.pending_press_lighting, "ready": self.ready,
                  "error": self.error, "message": self.message,
                  "warning": self.warning}
        result.update(extra)
        return result

    def toggle_key(self, n):
        """Apply the same toggle/switch rules for virtual and physical keys."""
        if not self.ready:
            raise RuntimeError(self.error or "The keypad is not connected.")
        if n == self.active:
            # Same key again: persist its pending mapping and/or color and turn it off.
            if self.pending or self.pending_color or self.pending_press_lighting is not None:
                self.persist_pending(n)
            self.active = None
            self.pending = None
            self.pending_color = None
            self.pending_press_lighting = None
        else:
            # Different key: discard the old preview and switch selection.
            if self.active is not None and self.pending_color:
                old_color = self.colors.get(self.active, "#FFFFFF").lstrip("#")
                r, g, b = (int(old_color[i:i + 2], 16) for i in (0, 2, 4))
                event = (self.device_module.LED_EVENT_PRESS_ON_RELEASE_OFF
                         if self.press_lighting[self.active] else self.device_module.LED_EVENT_NONE)
                self.device.write_led(self.active - 1, r, g, b, event=event)
            self.active = n
            self.pending = None
            self.pending_color = None
            self.pending_press_lighting = None
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
        # binding.
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
            elif self.path == "/api/color":
                n = int(data["key"])
                if not 1 <= n <= 12:
                    raise ValueError("Key number must be between 1 and 12.")
                color = str(data["color"])
                self.respond(app.set_color(n, color))
            elif self.path == "/api/press-lighting":
                n = int(data["key"])
                if not 1 <= n <= 12:
                    raise ValueError("Key number must be between 1 and 12.")
                self.respond(app.set_press_lighting(n, bool(data["enabled"])))
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
