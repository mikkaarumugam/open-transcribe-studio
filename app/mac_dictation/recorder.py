from __future__ import annotations

from array import array
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
        self._peak_sample = 0

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - platform dependency
            raise RuntimeError("Missing dependency: install sounddevice to record microphone audio") from exc

        self._frames = []
        self._peak_sample = 0

        def callback(indata, frames, time, status):  # pragma: no cover - callback exercised manually
            if status:
                print(status)
            chunk = bytes(indata)
            self._frames.append(chunk)
            samples = array("h")
            samples.frombytes(chunk)
            if samples:
                self._peak_sample = max(self._peak_sample, max(abs(sample) for sample in samples))

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
        )
        self._stream.start()
        try:
            device_info = sd.query_devices(self._stream.device, "input")
            print(f"[WhisperType] input device: {device_info.get('name', self._stream.device)}", flush=True)
        except Exception as exc:
            print(f"[WhisperType] could not read input device info: {exc}", flush=True)

    def stop(self) -> str:
        if self._stream is None:
            raise RuntimeError("Recorder was not started")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        total_bytes = sum(len(frame) for frame in self._frames)
        print(
            f"[WhisperType] captured audio chunks={len(self._frames)} bytes={total_bytes} peak={self._peak_sample}",
            flush=True,
        )

        output = Path(tempfile.mkstemp(prefix="whispertype-", suffix=".wav")[1])
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(b"".join(self._frames))
        return str(output)
