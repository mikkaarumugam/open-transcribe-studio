from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
from pathlib import Path


BUNDLE_IDENTIFIER = "com.mikka.open-transcribe-studio.whispertype"
BUNDLE_VERSION = "0.3.0"


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _c_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def render_launcher_script(
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> str:
    """Return a shell fallback launcher for non-macOS tests/dev environments."""
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


def render_native_launcher_source(
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> str:
    """Return C source for the real macOS CFBundleExecutable.

    Using a compiled executable avoids the AppleScript `do shell script` wrapper,
    which can cause macOS TCC microphone permission to attach to osascript/Python
    instead of the WhisperType.app bundle identity.
    """
    repo = _c_string(str(repo_dir))
    model_c = _c_string(model)
    hold_key_c = _c_string(hold_key)
    language_c = _c_string(language)
    return f'''#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void ensure_log_dir(void) {{
    const char *home = getenv("HOME");
    if (!home) return;
    char library[4096];
    char logs[4096];
    char app_logs[4096];
    snprintf(library, sizeof(library), "%s/Library", home);
    snprintf(logs, sizeof(logs), "%s/Library/Logs", home);
    snprintf(app_logs, sizeof(app_logs), "%s/Library/Logs/WhisperType", home);
    mkdir(library, 0755);
    mkdir(logs, 0755);
    mkdir(app_logs, 0755);
}}

static void open_log(void) {{
    ensure_log_dir();
    const char *home = getenv("HOME");
    if (!home) return;
    char log_path[4096];
    snprintf(log_path, sizeof(log_path), "%s/Library/Logs/WhisperType/launcher.log", home);
    freopen(log_path, "a", stdout);
    freopen(log_path, "a", stderr);
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
}}

int main(int argc, char **argv) {{
    (void)argc;
    (void)argv;
    open_log();
    printf("--- WhisperType native launch ---\\n");
    const char *repo = "{repo}";
    if (chdir(repo) != 0) {{
        fprintf(stderr, "repo path does not exist or cannot be opened: %s: %s\\n", repo, strerror(errno));
        return 1;
    }}
    printf("repo: %s\\n", repo);

    const char *python = ".venv/bin/python";
    if (access(python, X_OK) != 0) {{
        fprintf(stderr, "missing executable .venv/bin/python in %s\\n", repo);
        return 1;
    }}

    char virtual_env[4096];
    char path_env[8192];
    const char *old_path = getenv("PATH");
    snprintf(virtual_env, sizeof(virtual_env), "%s/.venv", repo);
    setenv("VIRTUAL_ENV", virtual_env, 1);
    snprintf(path_env, sizeof(path_env), "%s/.venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:%s", repo, old_path ? old_path : "");
    setenv("PATH", path_env, 1);
    setenv("PYTHONUNBUFFERED", "1", 1);

    execl(
        python,
        python,
        "-m",
        "app.mac_dictation.cli",
        "--model",
        "{model_c}",
        "--hold-key",
        "{hold_key_c}",
        "--language",
        "{language_c}",
        "--menubar",
        (char *)NULL
    );
    fprintf(stderr, "failed to exec %s: %s\\n", python, strerror(errno));
    return 1;
}}
'''


def _write_info_plist(contents: Path) -> None:
    info = {
        "CFBundleName": "WhisperType",
        "CFBundleDisplayName": "WhisperType",
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleVersion": BUNDLE_VERSION,
        "CFBundleShortVersionString": BUNDLE_VERSION,
        "CFBundleExecutable": "WhisperType",
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "WhisperType records while you hold fn so it can transcribe speech locally.",
        "NSAppleEventsUsageDescription": "WhisperType may use local automation only to show setup alerts.",
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)


def _prepare_bundle_dirs(app_path: Path) -> tuple[Path, Path, Path]:
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)
    _write_info_plist(contents)
    return contents, macos_dir, resources_dir


def _ad_hoc_codesign(app_path: Path) -> None:
    if platform.system() != "Darwin" or not shutil.which("codesign"):
        return
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        check=True,
    )


def _write_native_launcher_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    _, macos_dir, resources_dir = _prepare_bundle_dirs(app_path)
    source = render_native_launcher_source(
        repo_dir=repo_dir,
        model=model,
        hold_key=hold_key,
        language=language,
    )
    source_path = resources_dir / "WhisperTypeLauncher.c"
    source_path.write_text(source)
    executable = macos_dir / "WhisperType"
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        raise RuntimeError(
            "Building the portfolio-grade macOS app requires clang. Install Apple Command Line Tools with: xcode-select --install"
        )
    subprocess.run([clang, str(source_path), "-o", str(executable)], check=True)
    executable.chmod(executable.stat().st_mode | 0o755)
    _ad_hoc_codesign(app_path)
    return app_path


def _write_fallback_shell_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    _, macos_dir, _ = _prepare_bundle_dirs(app_path)
    launcher = macos_dir / "WhisperType"
    launcher.write_text(
        render_launcher_script(repo_dir=repo_dir, model=model, hold_key=hold_key, language=language)
    )
    launcher.chmod(launcher.stat().st_mode | 0o755)
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

    if platform.system() == "Darwin":
        return _write_native_launcher_app(
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
