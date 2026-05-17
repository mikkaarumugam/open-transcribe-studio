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
    assert "--model 'base'" in launcher.read_text()
