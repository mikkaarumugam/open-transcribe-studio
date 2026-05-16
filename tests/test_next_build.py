from pathlib import Path

from app.mac_dictation.app_bundle import (
    build_app_bundle,
    render_applescript_launcher,
    render_launcher_script,
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


def test_applescript_launcher_runs_zsh_launcher_for_double_click_apps():
    launcher = render_launcher_script(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="tiny",
        hold_key="fn",
        language="en",
    )
    applescript = render_applescript_launcher(launcher)

    assert 'do shell script "/bin/zsh -lc " & quoted form of' in applescript
    assert "WhisperType launch" in applescript
    assert ".venv/bin/python" in applescript

def test_build_app_bundle_writes_macos_app_structure(tmp_path):
    app_path = build_app_bundle(
        output_dir=tmp_path,
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert app_path == tmp_path / "WhisperType.app"
    assert (app_path / "Contents" / "Info.plist").exists()
    launcher = app_path / "Contents" / "MacOS" / "WhisperType"
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111
    assert "--model 'base'" in launcher.read_text()
