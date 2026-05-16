from app.mac_dictation.doctor import measure_microphone_peak


class FakeStream:
    def __init__(self, callback):
        self.callback = callback

    def start(self):
        self.callback((100).to_bytes(2, "little", signed=True), 1, None, None)

    def stop(self):
        pass

    def close(self):
        pass


class FakeSoundDevice:
    def query_devices(self, kind=None):
        return {"name": "Fake Mic"}

    def RawInputStream(self, samplerate, channels, dtype, callback):
        return FakeStream(callback)


def test_doctor_reports_microphone_peak(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice())
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    assert measure_microphone_peak(seconds=0) == 100
