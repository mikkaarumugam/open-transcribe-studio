from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def render_launcher_script(
    repo_dir: Path,
    model: str = "base",
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
REPO_DIR={quoted_repo}
if [ ! -d "$REPO_DIR" ]; then
  osascript -e "display alert \"WhisperType repo not found\" message \"The app was built for: $REPO_DIR. Rebuild it from the real open-transcribe-studio folder with: whispertype-build-app --repo-dir \\\"$PWD\\\" --model base --language en\""
  echo "repo path does not exist: $REPO_DIR"
  exit 1
fi
cd "$REPO_DIR"
echo "repo: $(pwd)"
if [ ! -x .venv/bin/python ]; then
  osascript -e 'display alert "WhisperType setup needed" message "Open Terminal, cd into the real open-transcribe-studio folder, then run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."'
  echo "missing .venv/bin/python in $(pwd)"
  exit 1
fi
source '.venv/bin/activate'
echo "python: $(.venv/bin/python --version)"
exec '.venv/bin/python' -m app.mac_dictation.cli --model {quoted_model} --hold-key {quoted_hold_key} --language {quoted_language} --menubar
"""

def render_applescript_launcher(shell_script: str) -> str:
    """Return AppleScript source for a double-clickable launcher app.

    LaunchServices is more reliable with an osacompile-built applet than with a
    raw shell script as CFBundleExecutable. The AppleScript delegates immediately
    to zsh so the rest of the launcher stays testable and shared.
    """
    escaped_script = shell_script.replace("\\", "\\\\").replace('"', '\\"')
    return f'''on run
	do shell script "/bin/zsh -lc " & quoted form of "{escaped_script}"
end run
'''


def _write_fallback_shell_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    info = {
        "CFBundleName": "WhisperType",
        "CFBundleDisplayName": "WhisperType",
        "CFBundleIdentifier": "com.mikka.whispertype",
        "CFBundleVersion": "0.2.1",
        "CFBundleShortVersionString": "0.2.1",
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


def _write_applescript_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    shell_script = render_launcher_script(
        repo_dir=repo_dir,
        model=model,
        hold_key=hold_key,
        language=language,
    )
    applescript = render_applescript_launcher(shell_script)
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "WhisperType.applescript"
        script_path.write_text(applescript)
        subprocess.run(["osacompile", "-o", str(app_path), str(script_path)], check=True)

    info_plist = app_path / "Contents" / "Info.plist"
    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    info.update(
        {
            "CFBundleName": "WhisperType",
            "CFBundleDisplayName": "WhisperType",
            "CFBundleIdentifier": "com.mikka.whispertype",
            "CFBundleVersion": "0.2.1",
            "CFBundleShortVersionString": "0.2.1",
            "LSUIElement": True,
            "NSMicrophoneUsageDescription": "WhisperType records while you hold fn so it can transcribe speech locally.",
        }
    )
    with info_plist.open("wb") as handle:
        plistlib.dump(info, handle)
    return app_path


def build_app_bundle(
    output_dir: Path,
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> Path:
    """Create a macOS app bundle that starts WhisperType without Terminal."""
    output_dir.mkdir(parents=True, exist_ok=True)
    app_path = output_dir / "WhisperType.app"
    if app_path.exists():
        shutil.rmtree(app_path)

    if platform.system() == "Darwin" and shutil.which("osacompile"):
        return _write_applescript_app(
            app_path=app_path,
            repo_dir=repo_dir,
            model=model,
            hold_key=hold_key,
            language=language,
        )

    return _write_fallback_shell_app(
        app_path=app_path,
        repo_dir=repo_dir,
        model=model,
        hold_key=hold_key,
        language=language,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a local WhisperType.app launcher")
    parser.add_argument("--output-dir", default="dist", help="Directory where WhisperType.app is written")
    parser.add_argument("--repo-dir", default=".", help="Path to this repository on your Mac")
    parser.add_argument("--model", default="base", help="Whisper model used by the app. Default: base for better dictation accuracy.")
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
