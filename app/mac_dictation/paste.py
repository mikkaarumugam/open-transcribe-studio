from __future__ import annotations

import platform
import subprocess


class MacClipboardTyper:
    """Paste text into the currently focused macOS app.

    Uses pbcopy for the clipboard, then posts a native Cmd+V keyboard event.
    This avoids AppleScript/System Events automation prompts, but still requires
    macOS Accessibility permission for the app/runtime running WhisperType.
    """

    def paste_text(self, text: str) -> None:
        print(f"[WhisperType] copying {len(text)} characters to clipboard", flush=True)
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        if platform.system() == "Darwin":
            print("[WhisperType] sending Cmd+V with Quartz", flush=True)
            self._press_cmd_v_with_quartz()
            print("[WhisperType] paste command sent", flush=True)
            return
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True,
        )

    def _press_cmd_v_with_quartz(self) -> None:  # pragma: no cover - macOS integration
        import Quartz

        v_keycode = 9
        source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        key_down = Quartz.CGEventCreateKeyboardEvent(source, v_keycode, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(source, v_keycode, False)
        Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(key_up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
