from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.mac_dictation.clean_text import clean_dictation_text


class Recorder(Protocol):
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
    is_recording: bool = False

    def on_fn_down(self) -> None:
        """Start recording when fn is pressed/held.

        Repeated key-down events are ignored until fn is released.
        """
        if self.is_recording:
            return
        self.is_recording = True
        self.recorder.start()

    def on_fn_up(self) -> None:
        """Stop recording when fn is released, then paste clean text."""
        if not self.is_recording:
            return
        self.is_recording = False
        audio_path = self.recorder.stop()
        raw_text = self.transcriber.transcribe(audio_path)
        clean_text = clean_dictation_text(raw_text)
        if clean_text:
            self.typer.paste_text(clean_text)
