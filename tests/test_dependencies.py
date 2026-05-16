from pathlib import Path


def test_macos_menu_bar_dependency_is_declared():
    pyproject = Path("pyproject.toml").read_text()

    assert "pyobjc-framework-Cocoa" in pyproject
    assert "pyobjc-framework-Quartz" in pyproject
