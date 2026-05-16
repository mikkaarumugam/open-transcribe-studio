from __future__ import annotations

from pathlib import Path


class LocalWhisperTranscriber:
    """Local faster-whisper adapter used by the global dictation tool."""

    def __init__(self, model_size: str = "tiny", language: str = "en", vad_filter: bool = False):
        self.model_size = model_size
        self.language = language
        self.vad_filter = vad_filter
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def warm_up(self) -> None:
        print(f"[WhisperType] loading Whisper model: {self.model_size}", flush=True)
        self._load_model()
        print(f"[WhisperType] Whisper model ready: {self.model_size}", flush=True)

    def transcribe(self, path: str) -> str:
        model = self._load_model()
        kwargs = {"beam_size": 5, "vad_filter": self.vad_filter, "task": "transcribe"}
        if self.language.lower() != "auto":
            kwargs["language"] = self.language
        print(f"[WhisperType] whisper kwargs: {kwargs}", flush=True)
        segments, _info = model.transcribe(str(Path(path)), **kwargs)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        print(f"[WhisperType] raw transcription: {text!r}", flush=True)
        return text
