from app.mac_dictation.clean_text import clean_dictation_text
from app.mac_dictation.controller import DictationController


class FakeRecorder:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.output_path = None

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
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer)

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
    controller = DictationController(recorder=recorder, transcriber=transcriber, typer=typer)

    controller.on_fn_down()
    controller.on_fn_down()
    controller.on_fn_up()

    assert recorder.started is True
    assert typer.text == "Hello world."
