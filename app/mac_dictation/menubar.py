from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from typing import Callable

from app.mac_dictation.controller import DictationController


class MenuBarUnavailableError(RuntimeError):
    """Raised when the macOS menu bar UI cannot be loaded."""


@dataclass
class WhisperTypeMenuBarApp:
    """Tiny native macOS menu bar wrapper around the existing hold-key listener."""

    run_listener: Callable[[], None]
    controller: DictationController | None = None
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
            from PyObjCTools.AppHelper import callAfter  # type: ignore[import-not-found]
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
            "WhisperType ready — hold fn to dictate", None, ""
        )
        menu.addItem_(running_item)
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit WhisperType", "terminate:", "q")
        menu.addItem_(quit_item)
        status_item.setMenu_(menu)

        def apply_status(status: str) -> None:
            labels = {
                "idle": (self.status_title, "WhisperType ready — hold fn to dictate"),
                "recording": ("🎙", "Recording… release fn to transcribe"),
                "transcribing": ("…", "Transcribing locally…"),
                "silence": ("⚠", "Captured silence — check microphone permission/input"),
                "error": ("!", "WhisperType error — check launcher.log"),
            }
            title, message = labels.get(status, (self.status_title, "WhisperType running"))
            status_item.button().setTitle_(title)
            running_item.setTitle_(message)

        if self.controller is not None:
            def notify_status(status: str) -> None:
                callAfter(apply_status, status)

            self.controller.on_status_change = notify_status

        listener_thread = threading.Thread(
            target=self._run_listener_with_logging,
            name="WhisperTypeListener",
            daemon=True,
        )
        listener_thread.start()
        app.run()
        _ = NSApp  # keep imported symbol referenced for pyobjc/linters
