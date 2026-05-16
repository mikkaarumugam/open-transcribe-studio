from __future__ import annotations

import argparse
import time

from app.mac_dictation.paste import MacClipboardTyper


def main() -> None:
    parser = argparse.ArgumentParser(description="Test WhisperType paste into the currently focused app")
    parser.add_argument(
        "--text",
        default="WhisperType paste test.",
        help="Text to paste after the countdown",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds to wait so you can click into a text field first",
    )
    args = parser.parse_args()

    print(f"Click into the target text field now. Pasting in {args.delay:.1f} seconds...")
    time.sleep(args.delay)
    MacClipboardTyper().paste_text(args.text)
    print("Paste command sent. If text did not appear, grant Accessibility permission to Terminal/Python/WhisperType.")


if __name__ == "__main__":
    main()
