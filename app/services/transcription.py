from __future__ import annotations

import uuid
from pathlib import Path

from app.models import Segment, TranscriptResult
from app.services.enrichment import extract_keywords, make_chapters, redact_pii, summarize_text


class TranscriptionError(RuntimeError):
    pass


def transcribe_file(path: Path, filename: str, model_size: str = "tiny") -> TranscriptResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - environment guard
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install -e '.[dev]'"
        ) from exc

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        raw_segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
        segments = [
            Segment(id=i, start=float(seg.start), end=float(seg.end), text=seg.text.strip())
            for i, seg in enumerate(raw_segments)
        ]
    except Exception as exc:  # pragma: no cover - depends on model/audio/ffmpeg
        raise TranscriptionError(f"Transcription failed: {exc}") from exc

    text = " ".join(segment.text for segment in segments).strip()
    return build_result(
        filename=filename,
        text=text,
        segments=segments,
        language=getattr(info, "language", None),
        duration=getattr(info, "duration", None),
    )


def build_result(
    filename: str,
    text: str,
    segments: list[Segment],
    language: str | None = None,
    duration: float | None = None,
) -> TranscriptResult:
    return TranscriptResult(
        job_id=str(uuid.uuid4()),
        filename=filename,
        language=language,
        duration=duration,
        text=text,
        redacted_text=redact_pii(text),
        summary=summarize_text(text),
        keywords=extract_keywords(text),
        chapters=make_chapters(segments),
        segments=segments,
    )
