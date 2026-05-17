from pathlib import Path

import pytest

from app.mac_dictation.model_config import (
    DEFAULT_MODEL,
    VALID_MODELS,
    load_model,
    save_model,
)


def test_default_model_is_base():
    assert DEFAULT_MODEL == "base"


def test_valid_models_cover_the_documented_sizes():
    assert set(VALID_MODELS) == {"tiny", "base", "small", "medium", "large-v3"}


def test_load_returns_default_when_file_missing(tmp_path: Path):
    assert load_model(tmp_path / "missing.txt") == DEFAULT_MODEL


def test_save_and_load_round_trip(tmp_path: Path):
    target = tmp_path / "nested" / "model.txt"
    save_model("small", target)
    assert target.exists()
    assert load_model(target) == "small"


def test_load_falls_back_to_default_when_file_contents_are_invalid(tmp_path: Path):
    target = tmp_path / "model.txt"
    target.write_text("not-a-real-model\n")
    assert load_model(target) == DEFAULT_MODEL


def test_save_rejects_unknown_model(tmp_path: Path):
    with pytest.raises(ValueError):
        save_model("super-large", tmp_path / "model.txt")
