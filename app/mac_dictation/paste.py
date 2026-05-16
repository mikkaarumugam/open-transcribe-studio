from __future__ import annotations

import subprocess


class MacClipboardTyper:
    """Paste text into the currently focused macOS app.

    Uses pbcopy for the clipboard and AppleScript to press Cmd+V. This requires
    macOS Accessibility permission for the terminal/app running WhisperType.
    """

    def paste_text(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True,
        )
