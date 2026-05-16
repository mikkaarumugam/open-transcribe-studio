from __future__ import annotations

import tempfile
import wave
from pathlib import Path


class WavHoldRecorder:
    """Record microphone audio to a temporary WAV file until stopped."""

    def __init__(self, sample_rate: int = 16_000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
        self._frames: list[bytes] = []

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - platform dependency
            raise RuntimeError("Missing dependency: install sounddevice to record microphone audio") from exc

        self._frames = []

        def callback(indata, frames, time, status):  # pragma: no cover - callback exercised manually
            if status:
                print(status)
            self._frames.append(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> str:
        if self._stream is None:
            raise RuntimeError("Recorder was not started")
        self._stream.stop()
        self._stream.close()
        self._stream = None

        output = Path(tempfile.mkstemp(prefix="whispertype-", suffix=".wav")[1])
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(b"".join(self._frames))
        return str(output)
