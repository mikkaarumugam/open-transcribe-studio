from __future__ import annotations

import argparse
import platform
from collections.abc import Callable

from app.mac_dictation.controller import DictationController
from app.mac_dictation.hotkey import HoldKeyListener
from app.mac_dictation.paste import MacClipboardTyper
from app.mac_dictation.recorder import WavHoldRecorder
from app.mac_dictation.whisper import LocalWhisperTranscriber


def create_controller(
    model: str = "tiny",
    language: str = "en",
    vad_filter: bool = False,
    min_record_seconds: float = 0.35,
) -> DictationController:
    return DictationController(
        recorder=WavHoldRecorder(),
        transcriber=LocalWhisperTranscriber(model_size=model, language=language, vad_filter=vad_filter),
        typer=MacClipboardTyper(),
        min_record_seconds=min_record_seconds,
    )


def create_listener_runner(controller: DictationController, hold_key: str) -> Callable[[], None]:
    is_macos = platform.system() == "Darwin"
    if is_macos and hold_key.lower() == "fn":
        from app.mac_dictation.macos_fn import MacFnEventTapListener

        return MacFnEventTapListener(controller=controller).run_forever
    return HoldKeyListener(controller=controller, hold_key=hold_key).run_forever


def main() -> None:
    parser = argparse.ArgumentParser(description="WhisperType: hold fn to dictate into any macOS app")
    parser.add_argument("--model", default="tiny", help="faster-whisper model size: tiny/base/small/medium/large-v3")
    parser.add_argument("--hold-key", default="fn", help="Key to hold for recording. Default: fn. Fallback examples: f18, option_r")
    parser.add_argument("--language", default="en", help="Transcription language code. Default: en. Use auto to enable Whisper auto-detection.")
    parser.add_argument("--vad-filter", action="store_true", help="Enable faster-whisper VAD filtering. Disabled by default for short live dictation clips.")
    parser.add_argument("--min-record-seconds", type=float, default=0.35, help="Ignore accidental fn taps shorter than this many seconds. Default: 0.35")
    parser.add_argument("--menubar", action="store_true", help="Run as a macOS menu bar app instead of a terminal foreground process")
    args = parser.parse_args()

    is_macos = platform.system() == "Darwin"
    if not is_macos:
        print("Warning: global paste is designed for macOS. Tests can run elsewhere, but the app should be used on your Mac.")

    controller = create_controller(
        model=args.model,
        language=args.language,
        vad_filter=args.vad_filter,
        min_record_seconds=args.min_record_seconds,
    )
    run_listener = create_listener_runner(controller=controller, hold_key=args.hold_key)

    if args.menubar:
        from app.mac_dictation.menubar import WhisperTypeMenuBarApp

        WhisperTypeMenuBarApp(run_listener=run_listener).run()
        return

    print("WhisperType is running.")
    print(f"Hold {args.hold_key} to record. Release {args.hold_key} to transcribe and paste.")
    print(f"Transcription language: {args.language}.")
    print(f"Ignoring fn taps shorter than {args.min_record_seconds:.2f} seconds.")

    if is_macos and args.hold_key.lower() == "fn":
        print("Using native macOS fn/Globe detection via Quartz flags.")
        print("If this fails, re-check Accessibility + Input Monitoring permissions, then quit/reopen Terminal.")
    else:
        print("Using generic key listener. If fn is not detected on your Mac, try: --hold-key f18")
    run_listener()


if __name__ == "__main__":
    main()
