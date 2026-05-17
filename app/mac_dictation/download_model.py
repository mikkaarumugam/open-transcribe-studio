"""
Background helper: downloads one faster-whisper model and exits.

The native WhisperType.app launcher forks this script when the user clicks
"Download X" in the menu bar. We don't render any UI here. Progress
visibility is provided to the user via two file conventions:

  * A lock file at  ~/.config/whispertype/downloading-{model}.lock  is
    created on start (containing this process's PID) and removed on exit.
    The native launcher checks this file when rebuilding the model menu
    to show "Downloading…" while a download is in flight.

  * Completion is observed by the launcher noticing that the HuggingFace
    cache directory for the model now exists. No success/failure file is
    written — the cache directory IS the success signal.

Usage:
    python -m app.mac_dictation.download_model --model medium
"""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
from pathlib import Path

from app.mac_dictation.model_config import CONFIG_DIR, VALID_MODELS


HF_CACHE_ROOT = Path.home() / ".cache" / "huggingface" / "hub"


def model_cache_dir(model: str) -> Path:
    """Where faster-whisper / huggingface_hub stores this model on disk."""
    return HF_CACHE_ROOT / f"models--Systran--faster-whisper-{model}"


def model_is_downloaded(model: str) -> bool:
    """True if the model already lives in the HF cache.

    We require both the cache directory and a non-empty `snapshots/`
    subdirectory, since `huggingface_hub` creates the parent dir before
    the actual blob download starts. Using snapshots/ avoids reporting
    a half-downloaded model as ready.
    """
    snapshots = model_cache_dir(model) / "snapshots"
    if not snapshots.is_dir():
        return False
    return any(snapshots.iterdir())


def lock_path(model: str) -> Path:
    return CONFIG_DIR / f"downloading-{model}.lock"


def write_lock(model: str, pid: int) -> Path:
    path = lock_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n")
    return path


def remove_lock(model: str) -> None:
    try:
        lock_path(model).unlink()
    except FileNotFoundError:
        pass


def _install_cleanup(model: str) -> None:
    """Make sure the lock is removed no matter how we exit."""
    atexit.register(remove_lock, model)

    def _handle(signum, _frame):
        remove_lock(model)
        # Re-raise default behavior so the process actually dies.
        sys.exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):
            # Some signals aren't available in all environments; harmless.
            pass


def download(model: str) -> int:
    """Trigger the faster-whisper download by instantiating the model.

    Returns 0 on success, non-zero on failure. Lock cleanup happens via
    atexit / signal handlers so partial failures still release the lock.
    """
    if model not in VALID_MODELS:
        print(f"[download_model] unknown model: {model!r}", flush=True)
        return 2

    write_lock(model, os.getpid())
    _install_cleanup(model)

    print(f"[download_model] downloading {model} via faster-whisper...", flush=True)
    try:
        from faster_whisper import WhisperModel

        WhisperModel(model, device="cpu", compute_type="int8")
    except Exception as exc:
        print(f"[download_model] failed: {exc}", flush=True)
        return 1
    print(f"[download_model] done: {model}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download a faster-whisper model in the background."
    )
    parser.add_argument("--model", required=True, help=f"One of: {', '.join(VALID_MODELS)}")
    args = parser.parse_args(argv)
    return download(args.model)


if __name__ == "__main__":
    sys.exit(main())
