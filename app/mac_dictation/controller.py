from __future__ import annotations

import os
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable, Protocol

from app.mac_dictation.clean_text import clean_dictation_text


class Recorder(Protocol):
    peak_sample: int

    def start(self) -> None: ...
    def stop(self) -> str: ...


class Transcriber(Protocol):
    def transcribe(self, path: str) -> str: ...


class Typer(Protocol):
    def paste_text(self, text: str) -> None: ...


@dataclass
class DictationController:
    recorder: Recorder
    transcriber: Transcriber
    typer: Typer
    min_record_seconds: float = 0.35
    clock: Callable[[], float] = monotonic
    on_status_change: Callable[[str], None] | None = None
    is_recording: bool = False
    _recording_started_at: float | None = field(default=None, init=False)

    def _set_status(self, status: str) -> None:
        if self.on_status_change is not None:
            self.on_status_change(status)

    def on_fn_down(self) -> None:
        """Start recording when fn is pressed/held.

        Repeated key-down events are ignored until fn is released.
        """
        if self.is_recording:
            return
        self.is_recording = True
        self._recording_started_at = self.clock()
        self._set_status("recording")
        print("[WhisperType] starting microphone recording", flush=True)
        try:
            self.recorder.start()
        except Exception:
            self.is_recording = False
            self._recording_started_at = None
            self._set_status("error")
            raise
        print("[WhisperType] microphone recording started", flush=True)

    def on_fn_up(self) -> None:
        """Stop recording when fn is released, then paste clean text."""
        if not self.is_recording:
            return
        self.is_recording = False
        started_at = self._recording_started_at
        self._recording_started_at = None
        print("[WhisperType] stopping microphone recording", flush=True)
        audio_path: str | None = None
        try:
            audio_path = self.recorder.stop()
            duration = self.clock() - started_at if started_at is not None else 0.0
            print(f"[WhisperType] saved recording: {audio_path} ({duration:.2f}s)", flush=True)
            if started_at is not None and duration < self.min_record_seconds:
                print(
                    f"[WhisperType] ignored short recording under {self.min_record_seconds:.2f}s",
                    flush=True,
                )
                return
            peak_sample = getattr(self.recorder, "peak_sample", None)
            if peak_sample == 0:
                self._set_status("silence")
                print(
                    "[WhisperType] recording peak was 0; skipping transcription because the app captured silence. "
                    "Check macOS Microphone permission/input source for WhisperType/Python.",
                    flush=True,
                )
                return
            self._set_status("transcribing")
            print("[WhisperType] transcribing recording", flush=True)
            raw_text = self.transcriber.transcribe(audio_path)
            clean_text = clean_dictation_text(raw_text)
            if clean_text:
                print(f"[WhisperType] pasting text: {clean_text!r}", flush=True)
                self.typer.paste_text(clean_text)
            else:
                print("[WhisperType] transcription was empty after cleanup", flush=True)
        finally:
            if audio_path is not None:
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass
            self._set_status("idle")
