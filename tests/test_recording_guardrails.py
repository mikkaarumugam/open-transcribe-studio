from app.mac_dictation.controller import DictationController


class FakeRecorder:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.peak_sample = 100

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1
        return "/tmp/fake-recording.wav"


class FakeTranscriber:
    def __init__(self, text="hello"):
        self.text = text
        self.calls = 0

    def transcribe(self, path):
        self.calls += 1
        return self.text


class FakeTyper:
    def __init__(self):
        self.pasted = []

    def paste_text(self, text):
        self.pasted.append(text)


def test_controller_ignores_accidental_tap_shorter_than_minimum_duration():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber("paste")
    typer = FakeTyper()
    now = [100.0]
    controller = DictationController(
        recorder=recorder,
        transcriber=transcriber,
        typer=typer,
        min_record_seconds=0.35,
        clock=lambda: now[0],
    )

    controller.on_fn_down()
    now[0] += 0.1
    controller.on_fn_up()

    assert recorder.starts == 1
    assert recorder.stops == 1
    assert transcriber.calls == 0
    assert typer.pasted == []


def test_controller_pastes_recordings_longer_than_minimum_duration():
    recorder = FakeRecorder()
    transcriber = FakeTranscriber("paste")
    typer = FakeTyper()
    now = [100.0]
    controller = DictationController(
        recorder=recorder,
        transcriber=transcriber,
        typer=typer,
        min_record_seconds=0.35,
        clock=lambda: now[0],
    )

    controller.on_fn_down()
    now[0] += 0.5
    controller.on_fn_up()

    assert transcriber.calls == 1
    assert typer.pasted == ["Paste."]
