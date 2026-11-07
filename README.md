# sayo-config

A Python app that opens its UI in a foreground browser window. The 2×6 grid is
made of twelve separate inline SVG key items and reads/writes SayoDevice 2×6V
bindings and per-key RGB LED lighting over USB HID.

Install the USB HID dependency, connect the keypad, then run:

```sh
python3 -m pip install -r requirements.txt
python3 sayo_config.py
```

Click a virtual key or press its corresponding key on the physical keypad to
select it. Ordinary Mac keyboard input never selects a key. The active SVG key
gets a red border and reveals the LED color wheel configurator.

- **Shortcut binding**: Press a shortcut on the Mac keyboard to preview it.
- **LED lighting**: Pick a color using the interactive color wheel, brightness slider, hex input, or preset swatches to preview it on the active key.
- **Saving**: Click the active key to save the new shortcut and/or LED color directly to the keypad's flash memory.

A shortcut is one key plus any combination of Ctrl, Shift, Option, and Command.
The Python process serves the local page while it is open; press Ctrl+C in the
terminal to stop it. Clicking or pressing a different key discards any previous
unsaved preview. To distinguish physical keypad presses from Mac keyboard
input, the app temporarily assigns each physical key a unique shortcut while it
runs. It restores the saved mappings before saving an edit and when the app
exits.
