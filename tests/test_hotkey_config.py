from pathlib import Path

from app.mac_dictation.hotkey_config import (
    HotkeyConfig,
    load_hotkey_config,
    save_hotkey_config,
)


def test_default_config_matches_fn_globe():
    config = HotkeyConfig.default()
    assert config.keycode == 179
    assert config.modifier_flags == 0
    assert config.use_fn_flag is True
    assert config.label == "fn"


def test_parse_round_trip_preserves_fields():
    original = HotkeyConfig(
        keycode=79,
        modifier_flags=0x100000,  # kCGEventFlagMaskCommand
        use_fn_flag=False,
        label="cmd+f18",
    )
    parsed = HotkeyConfig.parse(original.to_text())
    assert parsed == original


def test_parse_falls_back_to_default_when_file_is_garbage():
    parsed = HotkeyConfig.parse("not a number\nnope\nfoo\n")
    assert parsed == HotkeyConfig.default()


def test_parse_accepts_comments_and_blank_lines():
    text = (
        "# WhisperType hotkey config\n"
        "\n"
        "49\n"
        "1572864\n"
        "0\n"
        "cmd+shift+space\n"
    )
    parsed = HotkeyConfig.parse(text)
    assert parsed.keycode == 49
    assert parsed.modifier_flags == 1572864
    assert parsed.use_fn_flag is False
    assert parsed.label == "cmd+shift+space"


def test_parse_accepts_three_lines_and_synthesizes_label():
    parsed = HotkeyConfig.parse("80\n0\n0\n")
    assert parsed.keycode == 80
    assert parsed.label == "keycode 80"


def test_load_returns_default_when_file_missing(tmp_path: Path):
    config = load_hotkey_config(tmp_path / "missing.txt")
    assert config == HotkeyConfig.default()


def test_save_and_load_round_trip_via_disk(tmp_path: Path):
    target = tmp_path / "nested" / "hotkey.txt"
    config = HotkeyConfig(keycode=96, modifier_flags=0, use_fn_flag=False, label="f5")
    save_hotkey_config(config, target)
    assert target.exists()
    loaded = load_hotkey_config(target)
    assert loaded == config
