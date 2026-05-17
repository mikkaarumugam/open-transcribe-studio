import tempfile
from pathlib import Path

from app.mac_dictation.clean_text import clean_dictation_text
from app.mac_dictation.controller import DictationController


class FakeRecorder:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.output_path = None
        self.peak_sample = 100

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        self.output_path = "/tmp/fake-recording.wav"
        return self.output_path


class FakeTranscriber:
    def __init__(self):
        self.path = None

    def transcribe(self, path):
        self.path = path
        return " um hello world  "


class FakeTyper:
    def __init__(self):
        self.text = None

    def paste_text(self, text):
        self.text = text


def test_clean_dictation_text_removes_fillers_and_formats_sentence():
    assert clean_dictation_text(" um hello there this is a test ") == "Hello there this is a test."


def test_controller_records_while_fn_is_held_then_pastes_clean_text():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer, min_record_seconds=0)

    controller.on_fn_down()
    controller.on_fn_up()

    assert recorder.started is True
    assert recorder.stopped is True
    assert transcriber.path == "/tmp/fake-recording.wav"
    assert typer.text == "Hello world."


def test_controller_ignores_repeated_fn_down_until_key_is_released():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer, min_record_seconds=0)

    controller.on_fn_down()
    controller.on_fn_down()
    controller.on_fn_up()

    assert recorder.started is True
    assert typer.text == "Hello world."


def test_controller_emits_status_changes_for_menu_bar_indicator():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    statuses = []
    controller = DictationController(
        recorder=recorder,
        transcriber=transcriber,
        typer=typer,
        min_record_seconds=0,
        on_status_change=statuses.append,
    )

    controller.on_fn_down()
    controller.on_fn_up()

    assert statuses == ["recording", "transcribing", "idle"]


def test_controller_does_not_transcribe_or_paste_silent_recording():
    recorder = FakeRecorder()
    recorder.peak_sample = 0
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    statuses = []
    controller = DictationController(
        recorder=recorder,
        transcriber=transcriber,
        typer=typer,
        min_record_seconds=0,
        on_status_change=statuses.append,
    )

    controller.on_fn_down()
    controller.on_fn_up()

    assert transcriber.path is None
    assert typer.text is None
    assert statuses == ["recording", "silence", "idle"]


class TempFileRecorder:
    """Writes a real (empty) wav-like file so we can assert it gets deleted."""

    def __init__(self, peak_sample: int = 100):
        self.peak_sample = peak_sample
        self.output_path: str | None = None

    def start(self):
        pass

    def stop(self):
        fd, path = tempfile.mkstemp(prefix="whispertype-test-", suffix=".wav")
        with open(fd, "wb") as handle:
            handle.write(b"fake audio")
        self.output_path = path
        return path


def test_controller_deletes_temp_recording_after_transcription():
    recorder = TempFileRecorder()
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer, min_record_seconds=0)

    controller.on_fn_down()
    controller.on_fn_up()

    assert recorder.output_path is not None
    assert not Path(recorder.output_path).exists(), "temp wav should be cleaned up after transcription"


def test_controller_deletes_temp_recording_even_when_silent():
    recorder = TempFileRecorder(peak_sample=0)
    transcriber = FakeTranscriber()
    typer = FakeTyper()
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer, min_record_seconds=0)

    controller.on_fn_down()
    controller.on_fn_up()

    assert recorder.output_path is not None
    assert not Path(recorder.output_path).exists(), "silent capture should also be cleaned up"
