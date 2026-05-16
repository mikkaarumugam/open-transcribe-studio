from __future__ import annotations

import argparse
import platform

from app.mac_dictation.controller import DictationController
from app.mac_dictation.hotkey import HoldKeyListener
from app.mac_dictation.paste import MacClipboardTyper
from app.mac_dictation.recorder import WavHoldRecorder
from app.mac_dictation.whisper import LocalWhisperTranscriber


def main() -> None:
    parser = argparse.ArgumentParser(description="WhisperType: hold fn to dictate into any macOS app")
    parser.add_argument("--model", default="tiny", help="faster-whisper model size: tiny/base/small/medium/large-v3")
    parser.add_argument("--hold-key", default="fn", help="Key to hold for recording. Default: fn. Fallback examples: f18, option_r")
    args = parser.parse_args()

    if platform.system() != "Darwin":
        print("Warning: global paste is designed for macOS. Tests can run elsewhere, but the app should be used on your Mac.")

    controller = DictationController(
        recorder=WavHoldRecorder(),
        transcriber=LocalWhisperTranscriber(model_size=args.model),
        typer=MacClipboardTyper(),
    )
    print("WhisperType is running.")
    print(f"Hold {args.hold_key} to record. Release {args.hold_key} to transcribe and paste.")
    print("If fn is not detected on your Mac, try: --hold-key f18")
    HoldKeyListener(controller=controller, hold_key=args.hold_key).run_forever()


if __name__ == "__main__":
    main()
