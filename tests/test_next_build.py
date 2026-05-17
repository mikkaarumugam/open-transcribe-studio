from pathlib import Path
import plistlib

from app.mac_dictation.app_bundle import (
    BUNDLE_IDENTIFIER,
    build_app_bundle,
    render_launcher_script,
    render_native_launcher_source,
)
from app.mac_dictation.whisper import LocalWhisperTranscriber


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return [FakeSegment(" hello "), FakeSegment("world ")], object()


def test_local_whisper_forces_english_by_default():
    model = FakeWhisperModel()
    transcriber = LocalWhisperTranscriber(model_size="tiny")
    transcriber._model = model

    text = transcriber.transcribe("/tmp/audio.wav")

    assert text == "hello world"
    assert model.calls == [
        (
            "/tmp/audio.wav",
            {"beam_size": 5, "vad_filter": False, "language": "en", "task": "transcribe"},
        )
    ]


def test_local_whisper_can_disable_language_for_auto_detect():
    model = FakeWhisperModel()
    transcriber = LocalWhisperTranscriber(model_size="tiny", language="auto")
    transcriber._model = model

    transcriber.transcribe("/tmp/audio.wav")

    assert "language" not in model.calls[0][1]
    assert model.calls[0][1]["task"] == "transcribe"


def test_launcher_script_runs_python_module_from_repo_venv_without_terminal():
    launcher = render_launcher_script(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="tiny",
        hold_key="fn",
        language="en",
    )

    assert "REPO_DIR='/Users/mikka/open-transcribe-studio'" in launcher
    assert "repo path does not exist: $REPO_DIR" in launcher
    assert "LOG_FILE=\"$HOME/Library/Logs/WhisperType/launcher.log\"" in launcher
    assert "source '.venv/bin/activate'" in launcher
    assert "exec '.venv/bin/python' -m app.mac_dictation.cli --model 'tiny' --hold-key 'fn' --language 'en' --menubar" in launcher


def test_native_launcher_execs_repo_python_without_applescript_wrapper():
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert 'const char *repo = "/Users/mikka/open-transcribe-studio";' in source
    assert 'execl(' in source
    assert '".venv/bin/python"' in source
    assert '"app.mac_dictation.cli"' in source
    assert '"--native-worker"' in source
    assert '"--menubar"' not in source
    assert 'printf("--- WhisperType native launch ---\\n");' in source
    assert "NSStatusItem *statusItem" in source
    assert 'setTitle:@"WT"' in source
    assert 'do shell script' not in source
    assert 'osascript' not in source


def test_native_launcher_supports_configurable_hotkey_with_capture_ui():
    # The end-user goal: hotkey is configurable from the menu bar, persisted to
    # ~/.config/whispertype/hotkey.txt, and re-read on launch. Match logic
    # branches between the fn/Globe flag and arbitrary keycode+modifier chords.
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    # Config load/save
    assert "load_hotkey_config_from_disk" in source
    assert "save_hotkey_config_to_disk" in source
    assert ".config/whispertype/hotkey.txt" in source

    # Generalized match: keycode + modifier flags, plus fn/Globe special case.
    assert "current_hotkey.keycode" in source
    assert "current_hotkey.modifier_flags" in source
    assert "current_hotkey.use_fn_flag" in source
    assert "kCGEventFlagMaskCommand" in source
    assert "kCGEventFlagMaskShift" in source

    # Menu bar UI
    assert "Set hotkey" in source
    assert "setHotkey:" in source
    assert "addLocalMonitorForEventsMatchingMask" in source
    assert "NSEventMaskKeyDown" in source
    assert "NSEventMaskFlagsChanged" in source

    # Menu shows the current hotkey label and is refreshed after capture.
    assert "Hotkey: %s" in source
    assert "refreshHotkeyMenuLabel" in source


def test_native_launcher_owns_fn_event_tap_so_trust_attaches_to_bundle():
    # macOS TCC binds Input Monitoring trust to the binary that calls
    # CGEventTapCreate. The bundle must own that call so the user's grant
    # of "WhisperType" actually authorises the fn key listener (instead of
    # /Library/Frameworks/Python.framework/.../python3.13, which is what
    # .venv/bin/python resolves to).
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert "CGEventTapCreate(" in source
    assert "kCGEventFlagMaskSecondaryFn" in source
    assert "pipe(fn_pipe)" in source
    assert "dup2(fn_pipe[0], STDIN_FILENO)" in source
    assert 'write_hotkey_event("FN_DOWN")' in source
    assert 'write_hotkey_event("FN_UP")' in source
    assert "start_fn_event_tap();" in source


def test_native_launcher_source_has_valid_c_string_escapes():
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert 'printf("--- WhisperType native launch ---\\n");' in source
    assert 'fprintf(stderr, "repo path does not exist or cannot be opened: %s: %s\\n", repo, strerror(errno));' in source
    assert 'printf("repo: %s\\n", repo);' in source
    assert 'fprintf(stderr, "missing executable .venv/bin/python in %s\\n", repo);' in source
    assert 'fprintf(stderr, "failed to exec %s: %s\\n", python, strerror(errno));' in source


def test_build_app_bundle_writes_macos_app_structure(tmp_path):
    app_path = build_app_bundle(
        output_dir=tmp_path,
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert app_path == tmp_path / "WhisperType.app"
    info_plist = app_path / "Contents" / "Info.plist"
    assert info_plist.exists()
    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleIdentifier"] == BUNDLE_IDENTIFIER
    assert info["NSMicrophoneUsageDescription"]
    launcher = app_path / "Contents" / "MacOS" / "WhisperType"
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111
    # On Darwin the launcher is a compiled Obj-C binary; the rendered source
    # is stashed alongside it in Resources. On non-Darwin it is a shell script.
    source_file = app_path / "Contents" / "Resources" / "WhisperTypeLauncher.m"
    if source_file.exists():
        assert '"--model"' in source_file.read_text()
    else:
        assert "--model 'base'" in launcher.read_text()
