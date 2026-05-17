from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


CONFIG_DIR = Path.home() / ".config" / "whispertype"
CONFIG_PATH = CONFIG_DIR / "hotkey.txt"


@dataclass
class HotkeyConfig:
    """Shared on-disk hotkey description.

    The Obj-C launcher (inside WhisperType.app) and the Python worker both read
    this file. Keeping it as four plain text lines means the launcher does not
    need a JSON parser, and the user can hand-edit it.

    Line order:
        1. keycode (int) — macOS virtual keycode, e.g. 179 for fn/Globe, 79 for F18
        2. modifier_flags (int) — CGEventFlags mask, e.g. 0x100000 for cmd
        3. use_fn_flag (0/1) — true only for fn/Globe (matched via SecondaryFn flag)
        4. label (string) — display label for the menu bar, e.g. "fn" or "cmd+shift+space"
    """

    keycode: int
    modifier_flags: int
    use_fn_flag: bool
    label: str

    DEFAULT_KEYCODE: ClassVar[int] = 179
    DEFAULT_MODIFIER_FLAGS: ClassVar[int] = 0
    DEFAULT_USE_FN_FLAG: ClassVar[bool] = True
    DEFAULT_LABEL: ClassVar[str] = "fn"

    def to_text(self) -> str:
        return (
            f"{int(self.keycode)}\n"
            f"{int(self.modifier_flags)}\n"
            f"{1 if self.use_fn_flag else 0}\n"
            f"{self.label}\n"
        )

    @classmethod
    def default(cls) -> "HotkeyConfig":
        return cls(
            keycode=cls.DEFAULT_KEYCODE,
            modifier_flags=cls.DEFAULT_MODIFIER_FLAGS,
            use_fn_flag=cls.DEFAULT_USE_FN_FLAG,
            label=cls.DEFAULT_LABEL,
        )

    @classmethod
    def parse(cls, text: str) -> "HotkeyConfig":
        lines = [line.strip() for line in text.splitlines()]
        meaningful = [line for line in lines if line and not line.startswith("#")]
        if len(meaningful) < 3:
            return cls.default()
        try:
            keycode = int(meaningful[0])
            modifier_flags = int(meaningful[1])
            use_fn_flag = meaningful[2] in {"1", "true", "True", "yes"}
        except ValueError:
            return cls.default()
        label = meaningful[3] if len(meaningful) >= 4 else f"keycode {keycode}"
        return cls(
            keycode=keycode,
            modifier_flags=modifier_flags,
            use_fn_flag=use_fn_flag,
            label=label,
        )


def load_hotkey_config(path: Path = CONFIG_PATH) -> HotkeyConfig:
    try:
        text = path.read_text()
    except FileNotFoundError:
        return HotkeyConfig.default()
    return HotkeyConfig.parse(text)


def save_hotkey_config(config: HotkeyConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.to_text())
