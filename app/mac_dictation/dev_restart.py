from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


LOG_PATH = Path.home() / "Library" / "Logs" / "WhisperType" / "launcher.log"


def run(command: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, check=check)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fast local dev loop: pull, reinstall, kill, rebuild, open WhisperType, and tail logs."
    )
    parser.add_argument("--repo-dir", default=".", help="Path to open-transcribe-studio checkout")
    parser.add_argument("--model", default="base", help="Whisper model to build into the app")
    parser.add_argument("--language", default="en", help="Language code, or auto")
    parser.add_argument(
        "--hold-key",
        default="fn",
        help="Hold key to build into the app. On Mikka's Mac, '<179>' is the known fn/Globe fallback.",
    )
    parser.add_argument("--no-pull", action="store_true", help="Skip git pull")
    parser.add_argument("--no-install", action="store_true", help="Skip pip install -e .")
    parser.add_argument("--tail-lines", type=int, default=180, help="Number of log lines to print after launch")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser().resolve()
    if not repo_dir.exists():
        raise SystemExit(f"Repo not found: {repo_dir}")

    if not args.no_pull:
        run(["git", "pull"], cwd=repo_dir)
    if not args.no_install:
        run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=repo_dir)

    run(["osascript", "-e", 'quit app "WhisperType"'], cwd=repo_dir, check=False)
    run(["killall", "WhisperType"], cwd=repo_dir, check=False)
    run(["killall", "Python3"], cwd=repo_dir, check=False)
    run(["killall", "Python"], cwd=repo_dir, check=False)

    app_path = repo_dir / "dist" / "WhisperType.app"
    if app_path.exists():
        import shutil

        shutil.rmtree(app_path)

    build_command = [
        "whispertype-build-app",
        "--repo-dir",
        str(repo_dir),
        "--model",
        args.model,
        "--language",
        args.language,
        "--hold-key",
        args.hold_key,
    ]
    run(build_command, cwd=repo_dir)
    run(["open", str(app_path)], cwd=repo_dir)

    print("\nWhisperType relaunched.")
    print("Now press/hold your dictation key once, speak, release, then re-run this tail command if needed:")
    print(f"tail -{args.tail_lines} {LOG_PATH}")
    if LOG_PATH.exists():
        print("\n--- latest WhisperType log ---")
        subprocess.run(["tail", f"-{args.tail_lines}", str(LOG_PATH)], check=False)


if __name__ == "__main__":
    main()
