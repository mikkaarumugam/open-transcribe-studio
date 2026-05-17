from __future__ import annotations

from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "whispertype"
CONFIG_PATH = CONFIG_DIR / "model.txt"

VALID_MODELS = ("tiny", "base", "small", "medium", "large-v3")
DEFAULT_MODEL = "base"


def load_model(path: Path = CONFIG_PATH) -> str:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return DEFAULT_MODEL
    if text in VALID_MODELS:
        return text
    return DEFAULT_MODEL


def save_model(model: str, path: Path = CONFIG_PATH) -> None:
    if model not in VALID_MODELS:
        raise ValueError(f"unknown model: {model!r}; valid choices: {VALID_MODELS}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model + "\n")
