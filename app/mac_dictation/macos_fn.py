from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Callable

from app.mac_dictation.controller import DictationController

# macOS kCGEventFlagMaskSecondaryFn. PyObjC exposes this as
# Quartz.kCGEventFlagMaskSecondaryFn on modern macOS, but keeping the numeric
# constant here lets us unit-test the state machine on Linux too.
FN_FLAG_MASK = 1 << 23


@dataclass
class MacFnStateTracker:
    """Convert macOS modifier-flag changes into hold-to-record events."""

    controller: DictationController
    is_fn_down: bool = False
    on_state_change: Callable[[str], None] | None = None

    def handle_flags(self, flags: int) -> None:
        fn_down_now = bool(int(flags) & FN_FLAG_MASK)
        if fn_down_now and not self.is_fn_down:
            self.is_fn_down = True
            if self.on_state_change is not None:
                self.on_state_change("down")
            self.controller.on_fn_down()
        elif not fn_down_now and self.is_fn_down:
            self.is_fn_down = False
            if self.on_state_change is not None:
                self.on_state_change("up")
            self.controller.on_fn_up()


class MacFnEventTapListener:
    """Native macOS fn/Globe listener using Quartz event flags.

    pynput often reports fn as a release-only raw key like <63>, which is not
    enough for hold-to-record. Quartz exposes fn as a modifier flag, so this
    listener can detect both hold and release.
    """

    def __init__(self, controller: DictationController):
        self.tracker = MacFnStateTracker(
            controller,
            on_state_change=lambda state: print(f"[WhisperType] fn {state}", flush=True),
        )

    def _callback(self, proxy, event_type, event, refcon):  # pragma: no cover - macOS integration
        import Quartz

        if event_type == Quartz.kCGEventFlagsChanged:
            flags = Quartz.CGEventGetFlags(event)
            try:
                self.tracker.handle_flags(flags)
            except Exception:
                print("[WhisperType] fn event handler crashed", flush=True)
                traceback.print_exc()
        return event

    def run_forever(self) -> None:  # pragma: no cover - macOS integration
        import Quartz

        print("[WhisperType] starting native macOS fn event tap", flush=True)
        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            self._callback,
            None,
        )
        if tap is None:
            raise RuntimeError(
                "Could not create macOS event tap. Grant Accessibility and Input Monitoring "
                "permissions to WhisperType and Python 3, then quit and reopen WhisperType."
            )
        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(),
            run_loop_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(tap, True)
        print("[WhisperType] native macOS fn event tap is running", flush=True)
        Quartz.CFRunLoopRun()
