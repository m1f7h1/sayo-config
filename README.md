# sayo-config

A Python app that opens its UI in a foreground browser window. The 2×6 grid is
made of twelve separate inline SVG key items and reads/writes SayoDevice 2×6V
bindings over USB HID. It uses the protocol implementation in the sibling
`sayo-keyboard` project.

Install the USB HID dependency, connect the keypad, then run:

```sh
python3 -m pip install -r requirements.txt
python3 sayo_config.py
```

Click a virtual key or press its corresponding key on the physical keypad to
select it. Ordinary Mac keyboard input never selects a key. The active SVG key
gets a red border. Press a shortcut on
the Mac keyboard to preview it, then click the active key to save it. A shortcut
is one key plus any combination of Ctrl, Shift, Option, and Command. The Python
process serves the local page while it is open; press Ctrl+C in the terminal to
stop it. Clicking or pressing a different key discards the previous unsaved
preview. To distinguish physical keypad presses from Mac keyboard input, the
app temporarily assigns each physical key a unique shortcut while it runs. It
restores the saved mappings before saving an edit and when the app exits. The
current keypad firmware rejects the legacy LED read command, so the app leaves
physical lighting untouched and does not send LED commands.
