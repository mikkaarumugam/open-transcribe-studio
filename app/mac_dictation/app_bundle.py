from __future__ import annotations

import plistlib
from pathlib import Path


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def render_launcher_script(
    repo_dir: Path,
    model: str = "tiny",
    hold_key: str = "fn",
    language: str = "en",
) -> str:
    """Return the executable script used inside the macOS .app bundle.

    The bundle intentionally launches the project's editable install from the repo venv.
    That keeps the prototype free and easy to inspect instead of hiding it in a paid
    packaging toolchain.
    """
    quoted_repo = _single_quote(str(repo_dir))
    quoted_model = _single_quote(model)
    quoted_hold_key = _single_quote(hold_key)
    quoted_language = _single_quote(language)
    return f"""#!/bin/zsh
set -e
LOG_DIR="$HOME/Library/Logs/WhisperType"
LOG_FILE="$HOME/Library/Logs/WhisperType/launcher.log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1
echo "--- WhisperType launch $(date) ---"
cd {quoted_repo}
echo "repo: $(pwd)"
if [ ! -x .venv/bin/python ]; then
  osascript -e 'display alert "WhisperType setup needed" message "Open Terminal, cd into open-transcribe-studio, then run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."'
  echo "missing .venv/bin/python"
  exit 1
fi
source '.venv/bin/activate'
echo "python: $(.venv/bin/python --version)"
exec '.venv/bin/python' -m app.mac_dictation.cli --model {quoted_model} --hold-key {quoted_hold_key} --language {quoted_language} --menubar
"""


def build_app_bundle(
    output_dir: Path,
    repo_dir: Path,
    model: str = "tiny",
    hold_key: str = "fn",
    language: str = "en",
) -> Path:
    """Create a minimal macOS app bundle that starts WhisperType without Terminal."""
    app_path = output_dir / "WhisperType.app"
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    info = {
        "CFBundleName": "WhisperType",
        "CFBundleDisplayName": "WhisperType",
        "CFBundleIdentifier": "com.mikka.whispertype",
        "CFBundleVersion": "0.2.0",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleExecutable": "WhisperType",
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "WhisperType records while you hold fn so it can transcribe speech locally.",
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)

    launcher = macos_dir / "WhisperType"
    launcher.write_text(
        render_launcher_script(repo_dir=repo_dir, model=model, hold_key=hold_key, language=language)
    )
    launcher.chmod(launcher.stat().st_mode | 0o755)
    return app_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a local WhisperType.app launcher")
    parser.add_argument("--output-dir", default="dist", help="Directory where WhisperType.app is written")
    parser.add_argument("--repo-dir", default=".", help="Path to this repository on your Mac")
    parser.add_argument("--model", default="tiny", help="Whisper model used by the app")
    parser.add_argument("--hold-key", default="fn", help="Hold key used by the app")
    parser.add_argument("--language", default="en", help="Language code, or auto for detection")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()
    app_path = build_app_bundle(
        output_dir=output_dir,
        repo_dir=repo_dir,
        model=args.model,
        hold_key=args.hold_key,
        language=args.language,
    )
    print(f"Built {app_path}")


if __name__ == "__main__":
    main()
