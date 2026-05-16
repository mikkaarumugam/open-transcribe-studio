#!/usr/bin/env python3
"""Print key names seen by pynput so you can discover your Mac's fn/Globe mapping.

Run on macOS after granting Input Monitoring permission:

    python scripts/detect_keys.py

Press fn/Globe and any fallback keys. Copy the printed key name into:

    whispertype --hold-key <name>
"""

from pynput import keyboard


def normalise_key(key):
    name = getattr(key, "name", None)
    if name:
        return name.lower()
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    return str(key).lower().replace("key.", "")


def on_press(key):
    print(f"press: raw={key!r} normalised={normalise_key(key)}", flush=True)


def on_release(key):
    print(f"release: raw={key!r} normalised={normalise_key(key)}", flush=True)
    if key == keyboard.Key.esc:
        return False


print("Press keys to inspect them. Press Esc to quit.")
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
