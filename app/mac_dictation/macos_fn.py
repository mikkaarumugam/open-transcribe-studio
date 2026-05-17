from __future__ import annotations

import sys
import traceback
import threading
from dataclasses import dataclass
from typing import Callable, TextIO

from app.mac_dictation.controller import DictationController

# macOS kCGEventFlagMaskSecondaryFn. PyObjC exposes this as
# Quartz.kCGEventFlagMaskSecondaryFn on modern macOS, but keeping the numeric
# constant here lets us unit-test the state machine on Linux too.
FN_FLAG_MASK = 1 << 23
FN_KEYCODE = 63
FN_FALLBACK_KEYCODES = {63, 179}


def parse_fn_fallback_keycodes(hold_key: str = "fn") -> set[int]:
    """Return raw keycodes that should be treated as fn/Globe.

    `scripts/detect_keys.py` prints raw keys as strings like `<179>`. Passing
    `--hold-key '<179>'` should still use the native Quartz listener, not the
    generic pynput listener that requires a different accessibility trust path.
    """
    key = hold_key.strip().lower()
    fallback_keycodes = set(FN_FALLBACK_KEYCODES)
    if key in {"fn", "globe"}:
        return fallback_keycodes
    if key.startswith("<") and key.endswith(">"):
        key = key[1:-1]
    try:
        fallback_keycodes.add(int(key))
    except ValueError:
        pass
    return fallback_keycodes


@dataclass
class MacFnStateTracker:
    """Convert macOS modifier-flag changes into hold-to-record events."""

    controller: DictationController
    is_fn_down: bool = False
    on_state_change: Callable[[str], None] | None = None
    fallback_keycodes: set[int] | None = None

    def __post_init__(self) -> None:
        if self.fallback_keycodes is None:
            self.fallback_keycodes = set(FN_FALLBACK_KEYCODES)

    def _set_fn_down(self, fn_down_now: bool) -> None:
        if fn_down_now and not self.is_fn_down:
            self.is_fn_down = True
            if self.on_state_change is not None:
                self.on_state_change("down")
            self.controller.on_fn_down()
        elif not fn_down_now and self.is_fn_down:
            self.is_fn_down = False
            if self.on_state_change is not None:
                self.on_state_change("up")
            threading.Thread(
                target=self.controller.on_fn_up,
                name="WhisperTypeTranscription",
                daemon=True,
            ).start()

    def handle_flags(self, flags: int) -> None:
        self.handle_event(flags=flags, keycode=None)

    def handle_event(self, flags: int, keycode: int | None = None) -> None:
        fn_down_now = bool(int(flags) & FN_FLAG_MASK)
        if keycode in self.fallback_keycodes and not fn_down_now:
            # Some Mac keyboards expose Globe/Fn as a flagsChanged event with
            # a raw keycode but without kCGEventFlagMaskSecondaryFn. In that
            # case the press and release arrive as two fallback-key events, so
            # toggle state rather than waiting for a flag bit that never appears.
            fn_down_now = not self.is_fn_down
        self._set_fn_down(fn_down_now)

    def handle_key_down(self, keycode: int) -> None:
        if keycode in self.fallback_keycodes:
            self._set_fn_down(True)

    def handle_key_up(self, keycode: int) -> None:
        if keycode in self.fallback_keycodes:
            self._set_fn_down(False)


class MacFnEventTapListener:
    """Native macOS fn/Globe listener using Quartz event flags.

    pynput often reports fn as a release-only raw key like <63>, which is not
    enough for hold-to-record. Quartz exposes fn as a modifier flag, so this
    listener can detect both hold and release.
    """

    def __init__(self, controller: DictationController, hold_key: str = "fn"):
        fallback_keycodes = parse_fn_fallback_keycodes(hold_key)
        self.tracker = MacFnStateTracker(
            controller,
            on_state_change=lambda state: print(f"[WhisperType] fn {state}", flush=True),
            fallback_keycodes=fallback_keycodes,
        )
        print(
            f"[WhisperType] native fn fallback keycodes: {sorted(fallback_keycodes)}",
            flush=True,
        )

    def _callback(self, proxy, event_type, event, refcon):  # pragma: no cover - macOS integration
        import Quartz

        try:
            if event_type == Quartz.kCGEventFlagsChanged:
                flags = Quartz.CGEventGetFlags(event)
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                self.tracker.handle_event(flags=flags, keycode=keycode)
            elif event_type == Quartz.kCGEventKeyDown:
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                self.tracker.handle_key_down(keycode)
            elif event_type == Quartz.kCGEventKeyUp:
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                self.tracker.handle_key_up(keycode)
        except Exception:
            print("[WhisperType] fn event handler crashed", flush=True)
            traceback.print_exc()
        return event

    def run_forever(self) -> None:  # pragma: no cover - macOS integration
        import Quartz

        print("[WhisperType] starting native macOS fn event tap", flush=True)
        event_mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
        )
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


class StdinFnListener:
    """Read fn down/up events from stdin.

    Used when the WhisperType.app bundle launches us as a child process. The
    bundle's Obj-C launcher owns the CGEventTap (so macOS Input Monitoring trust
    attaches to the .app, not to /Library/Frameworks/Python.framework/...), and
    forwards each fn transition to this worker as a line: ``FN_DOWN`` or
    ``FN_UP``.
    """

    def __init__(self, controller: DictationController, stream: TextIO | None = None):
        self.tracker = MacFnStateTracker(
            controller,
            on_state_change=lambda state: print(f"[WhisperType] fn {state}", flush=True),
            fallback_keycodes={FN_KEYCODE, 179},
        )
        self.stream = stream if stream is not None else sys.stdin

    def run_forever(self) -> None:
        print("[WhisperType] reading fn events from launcher pipe (stdin)", flush=True)
        for raw in self.stream:
            line = raw.strip()
            if not line:
                continue
            if line == "FN_DOWN":
                self.tracker.handle_key_down(179)
            elif line == "FN_UP":
                self.tracker.handle_key_up(179)
            else:
                print(f"[WhisperType] ignored launcher message: {line!r}", flush=True)
        print("[WhisperType] launcher pipe closed; native worker exiting", flush=True)
