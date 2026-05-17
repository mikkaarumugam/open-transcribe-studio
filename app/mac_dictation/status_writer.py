from __future__ import annotations

import os
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "whispertype"
STATUS_PATH = CONFIG_DIR / "status.txt"


def write_status(status: str, path: Path = STATUS_PATH) -> None:
    """Write a one-word status string atomically.

    The Obj-C launcher polls this file every ~250ms and updates the WT menu
    bar title so the user can see when WhisperType is recording, transcribing,
    or idle. Atomic write avoids the launcher reading a half-written file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(status + "\n")
        os.replace(tmp, path)
    except OSError:
        pass
