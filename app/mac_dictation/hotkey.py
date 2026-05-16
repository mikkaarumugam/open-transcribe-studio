from __future__ import annotations

from app.mac_dictation.controller import DictationController


def _normalise_key(key) -> str:
    name = getattr(key, "name", None)
    if name:
        return name.lower()
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    return str(key).lower().replace("key.", "")


class HoldKeyListener:
    """Listen for press-and-hold dictation key events.

    Default target is macOS fn/globe. Some Macs/terminal permission setups do
    not expose fn to Python listeners; pass --hold-key f18 or --hold-key option_r
    as a fallback if your machine maps Globe/Fn differently.
    """

    def __init__(self, controller: DictationController, hold_key: str = "fn"):
        self.controller = controller
        self.hold_key = hold_key.lower()

    def _matches(self, key) -> bool:
        return _normalise_key(key) == self.hold_key

    def on_press(self, key) -> None:
        if self._matches(key):
            self.controller.on_fn_down()

    def on_release(self, key) -> None:
        if self._matches(key):
            self.controller.on_fn_up()

    def run_forever(self) -> None:  # pragma: no cover - manual macOS integration
        from pynput import keyboard
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
