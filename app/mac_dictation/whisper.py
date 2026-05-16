from __future__ import annotations

from pathlib import Path


class LocalWhisperTranscriber:
    """Local faster-whisper adapter used by the global dictation tool."""

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, path: str) -> str:
        model = self._load_model()
        segments, _info = model.transcribe(str(Path(path)), beam_size=5, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()
