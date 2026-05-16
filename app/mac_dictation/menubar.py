from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from typing import Callable


class MenuBarUnavailableError(RuntimeError):
    """Raised when the macOS menu bar UI cannot be loaded."""


@dataclass
class WhisperTypeMenuBarApp:
    """Tiny native macOS menu bar wrapper around the existing hold-key listener."""

    run_listener: Callable[[], None]
    status_title: str = "WT"

    def _run_listener_with_logging(self) -> None:
        try:
            self.run_listener()
        except Exception:
            print("[WhisperType] listener crashed", flush=True)
            traceback.print_exc()

    def run(self) -> None:
        try:
            from AppKit import (  # type: ignore[import-not-found]
                NSApp,
                NSApplication,
                NSMenu,
                NSMenuItem,
                NSStatusBar,
                NSVariableStatusItemLength,
            )
        except Exception as exc:  # pragma: no cover - exercised on macOS manually
            raise MenuBarUnavailableError(
                "Menu bar mode needs macOS PyObjC/AppKit. Install with: pip install -e ."
            ) from exc

        app = NSApplication.sharedApplication()
        status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        status_item.button().setTitle_(self.status_title)

        menu = NSMenu.alloc().init()
        running_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "WhisperType running — hold fn to dictate", None, ""
        )
        menu.addItem_(running_item)
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit WhisperType", "terminate:", "q")
        menu.addItem_(quit_item)
        status_item.setMenu_(menu)

        listener_thread = threading.Thread(
            target=self._run_listener_with_logging,
            name="WhisperTypeListener",
            daemon=True,
        )
        listener_thread.start()
        app.run()
        _ = NSApp  # keep imported symbol referenced for pyobjc/linters
