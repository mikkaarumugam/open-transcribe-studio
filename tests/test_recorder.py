from app.mac_dictation.recorder import WavHoldRecorder


class FakeSoundDevice:
    def __init__(self, default_samplerate=48000.0):
        self.default_samplerate = default_samplerate

    def query_devices(self, device=None, kind=None):
        assert kind == "input"
        return {"name": "Fake Mic", "default_samplerate": self.default_samplerate}


def test_recorder_uses_input_device_default_sample_rate_when_not_overridden():
    recorder = WavHoldRecorder(sample_rate=None)

    resolved = recorder._resolve_sample_rate(FakeSoundDevice(default_samplerate=48000.0))

    assert resolved == 48000
    assert recorder.sample_rate == 48000


def test_recorder_keeps_explicit_sample_rate_override():
    recorder = WavHoldRecorder(sample_rate=16000)

    resolved = recorder._resolve_sample_rate(FakeSoundDevice(default_samplerate=48000.0))

    assert resolved == 16000
    assert recorder.sample_rate == 16000


def test_recorder_logs_resolved_sample_rate(capsys):
    recorder = WavHoldRecorder(sample_rate=48000)

    recorder._log_sample_rate()

    assert "[WhisperType] recording sample rate: 48000 Hz" in capsys.readouterr().out
